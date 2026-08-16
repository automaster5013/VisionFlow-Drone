from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from types import SimpleNamespace

import numpy as np

from app.domain import FramePacket, InferencePacket, VideoSourceType
from app.inference.phase3_association import TrackedPersonBox
from app.inference.phase3_depth_enrichment import (
    DepthBucket,
    DepthEnrichmentResult,
    DepthMeasurement,
)
from app.inference.phase3_evidence import TrackPpeSnapshot
from app.inference.phase3_observability import Phase3ConsoleObserver
from app.inference.phase3_policy import (
    PpeComplianceState,
    PpeDecision,
)
from app.inference.phase3_ppe_depth import (
    DepthTriggerAttempt,
    PpeDepthFrameResult,
)
from app.inference.phase3_processor import (
    PpeFrameResult,
    PpeTrackAssessment,
)


class _FakePhase3Reporter:
    def __init__(self) -> None:
        self.events = []
        self.depths = []

    def submit_event(self, payload) -> None:
        self.events.append(payload)

    def submit_depth(self, event_key, payload) -> None:
        self.depths.append((event_key, payload))


def _inference() -> InferencePacket:
    frame = FramePacket(
        source_id="camera-1",
        session_id="session-1",
        source_type=VideoSourceType.DUMMY_VIDEO,
        drone_id=1,
        frame_index=27,
        captured_at=datetime(2026, 8, 16, tzinfo=UTC),
        image=np.zeros((8, 12, 3), dtype=np.uint8),
    )
    return InferencePacket(
        frame=frame,
        detections=(),
        inference_ms=4.2,
        annotated_image=frame.image.copy(),
    )


def _snapshot() -> TrackPpeSnapshot:
    decision = PpeDecision(
        state=PpeComplianceState.CONFIRMED_NO_HELMET,
        sample_count=10,
        helmet_rate=0.0,
        head_rate=1.0,
        head_no_helmet_rate=1.0,
        unknown_rate=0.0,
        current_streak_seconds=0.9,
        max_streak_seconds=0.9,
        reason="confirmed",
    )
    return TrackPpeSnapshot(
        track_id=1,
        sample_count=10,
        helmet_count=0,
        head_count=10,
        vest_count=0,
        head_no_helmet_count=10,
        unknown_count=0,
        helmet_rate=0.0,
        head_rate=1.0,
        vest_rate=0.0,
        head_no_helmet_rate=1.0,
        unknown_rate=0.0,
        current_streak_start_frame=1,
        current_streak_end_frame=28,
        current_streak_seconds=0.9,
        max_streak_start_frame=1,
        max_streak_end_frame=28,
        max_streak_seconds=0.9,
        last_sample_frame=28,
        decision=decision,
    )


def _analysis(*, accepted: bool = True):
    assessment = PpeTrackAssessment(
        track=TrackedPersonBox(
            track_id=1,
            x1=10,
            y1=10,
            x2=100,
            y2=200,
        ),
        snapshot=_snapshot(),
    )
    ppe = PpeFrameResult(
        frame_index=28,
        assessments=(assessment,),
        unassigned_count=0,
        ignored_count=0,
    )
    depth = PpeDepthFrameResult(
        ppe=ppe,
        depth_triggers=(
            DepthTriggerAttempt(
                track_id=1,
                event_key="camera-1:session-1:NO_HELMET:1",
                accepted=accepted,
            ),
        ),
        active_depth_tracks=(1,) if accepted else (),
    )
    return SimpleNamespace(
        inference=_inference(),
        ppe=depth,
        ppe_sampled=True,
    )


def test_record_analysis_emits_confirmed_ppe_trigger() -> None:
    stream = StringIO()
    observer = Phase3ConsoleObserver(stream=stream)

    observer.record_analysis(_analysis())

    output = stream.getvalue()
    snapshot = observer.snapshot()

    assert "PHASE3_PPE_TRIGGER" in output
    assert "TRACK_ID=1" in output
    assert "FRAME=28" in output
    assert "STATE=CONFIRMED_NO_HELMET" in output
    assert "ACCEPTED=true" in output
    assert "NO_HELMET_RATE=100.0%" in output
    assert "STREAK_SEC=0.900" in output
    assert snapshot.frames_analyzed == 1
    assert snapshot.ppe_samples == 1
    assert snapshot.depth_trigger_attempts == 1
    assert snapshot.depth_triggers_accepted == 1


def test_rejected_trigger_is_counted_and_visible() -> None:
    stream = StringIO()
    observer = Phase3ConsoleObserver(stream=stream)

    observer.record_analysis(_analysis(accepted=False))

    output = stream.getvalue()
    snapshot = observer.snapshot()

    assert "ACCEPTED=false" in output
    assert snapshot.depth_triggers_rejected == 1
    assert snapshot.depth_triggers_accepted == 0


def test_non_ppe_frame_only_updates_frame_counter() -> None:
    stream = StringIO()
    observer = Phase3ConsoleObserver(stream=stream)

    observer.record_analysis(
        SimpleNamespace(
            inference=_inference(),
            ppe=None,
            ppe_sampled=False,
        )
    )

    snapshot = observer.snapshot()
    assert stream.getvalue() == ""
    assert snapshot.frames_analyzed == 1
    assert snapshot.ppe_samples == 0
    assert snapshot.depth_trigger_attempts == 0


def test_depth_result_is_emitted_with_latency_and_bucket() -> None:
    stream = StringIO()
    observer = Phase3ConsoleObserver(stream=stream)

    observer.on_depth_result(
        DepthEnrichmentResult(
            event_key="camera-1:session-1:NO_HELMET:1",
            track_id=1,
            frame_index=28,
            event_time_sec=0.933,
            person_box=TrackedPersonBox(
                track_id=1,
                x1=10,
                y1=10,
                x2=100,
                y2=200,
            ),
            measurement=DepthMeasurement(
                estimated_depth_m=1.844,
                scene_q33_m=1.648,
                scene_q66_m=2.170,
                bucket=DepthBucket.MID,
            ),
            enrichment_latency_ms=62.36,
        )
    )

    output = stream.getvalue()
    snapshot = observer.snapshot()

    assert "PHASE3_DEPTH_RESULT" in output
    assert "EST_DEPTH_M=1.844" in output
    assert "Q33_M=1.648" in output
    assert "Q66_M=2.170" in output
    assert "DEPTH_BUCKET=MID" in output
    assert "ENRICHMENT_LATENCY_MS=62.36" in output
    assert snapshot.depth_results == 1


def test_emit_summary_reports_all_counters() -> None:
    stream = StringIO()
    observer = Phase3ConsoleObserver(stream=stream)

    observer.record_analysis(_analysis())
    observer.emit_summary()

    output = stream.getvalue()

    assert "PHASE3_SUMMARY" in output
    assert "FRAMES_ANALYZED=1" in output
    assert "PPE_SAMPLES=1" in output
    assert "DEPTH_TRIGGER_ATTEMPTS=1" in output
    assert "DEPTH_TRIGGERS_ACCEPTED=1" in output
    assert "DEPTH_TRIGGERS_REJECTED=0" in output
    assert "DEPTH_RESULTS=0" in output


def test_ppe_trigger_is_forwarded_to_phase3_reporter() -> None:
    reporter = _FakePhase3Reporter()
    observer = Phase3ConsoleObserver(
        stream=StringIO(),
        reporter=reporter,
    )

    observer.record_analysis(_analysis())

    assert len(reporter.events) == 1

    payload = reporter.events[0]
    assert payload["eventKey"] == "camera-1:session-1:NO_HELMET:1"
    assert payload["sourceId"] == "camera-1"
    assert payload["sessionId"] == "session-1"
    assert payload["sourceType"] == "DUMMY_VIDEO"
    assert payload["droneId"] == 1
    assert payload["trackId"] == 1
    assert payload["frameIndex"] == 28
    assert payload["ppeState"] == "CONFIRMED_NO_HELMET"
    assert payload["noHelmetRate"] == 1.0
    assert payload["helmetRate"] == 0.0
    assert payload["unknownRate"] == 0.0
    assert payload["streakSeconds"] == 0.9

def test_depth_result_is_forwarded_to_phase3_reporter() -> None:
    reporter = _FakePhase3Reporter()
    observer = Phase3ConsoleObserver(
        stream=StringIO(),
        reporter=reporter,
    )

    observer.on_depth_result(
        DepthEnrichmentResult(
            event_key="camera-1:session-1:NO_HELMET:1",
            track_id=1,
            frame_index=28,
            event_time_sec=0.933,
            person_box=TrackedPersonBox(
                track_id=1,
                x1=10,
                y1=10,
                x2=100,
                y2=200,
            ),
            measurement=DepthMeasurement(
                estimated_depth_m=1.844,
                scene_q33_m=1.648,
                scene_q66_m=2.170,
                bucket=DepthBucket.MID,
            ),
            enrichment_latency_ms=66.44,
        )
    )

    assert len(reporter.depths) == 1

    event_key, payload = reporter.depths[0]

    assert event_key == "camera-1:session-1:NO_HELMET:1"
    assert payload["estimatedDepthM"] == 1.844
    assert payload["sceneQ33M"] == 1.648
    assert payload["sceneQ66M"] == 2.170
    assert payload["depthBucket"] == "MID"
    assert payload["enrichmentLatencyMs"] == 66.44
