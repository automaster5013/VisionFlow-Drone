from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from typing import Protocol, TextIO

from app.domain import InferencePacket
from app.inference.phase3_depth_enrichment import DepthEnrichmentResult
from app.inference.phase3_pose import Phase3PoseFrameResult
from app.inference.phase3_ppe_depth import PpeDepthFrameResult
from app.phase3_reporting import Phase3EventReporterLike


class Phase3AnalysisLike(Protocol):
    inference: InferencePacket
    ppe: PpeDepthFrameResult | None
    ppe_sampled: bool
    pose: Phase3PoseFrameResult | None
    pose_sampled: bool


@dataclass(frozen=True, slots=True)
class Phase3ObservabilitySnapshot:
    frames_analyzed: int
    ppe_samples: int
    pose_samples: int
    pose_assigned: int
    pose_unassigned: int
    depth_trigger_attempts: int
    depth_triggers_accepted: int
    depth_triggers_rejected: int
    depth_results: int


class Phase3ConsoleObserver:
    def __init__(
        self,
        *,
        stream: TextIO | None = None,
        reporter: Phase3EventReporterLike | None = None,
    ) -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._reporter = reporter
        self._lock = threading.Lock()

        self._frames_analyzed = 0
        self._ppe_samples = 0
        self._pose_samples = 0
        self._pose_assigned = 0
        self._pose_unassigned = 0
        self._depth_trigger_attempts = 0
        self._depth_triggers_accepted = 0
        self._depth_triggers_rejected = 0
        self._depth_results = 0

    def record_analysis(self, analysis: Phase3AnalysisLike) -> None:
        with self._lock:
            self._frames_analyzed += 1
            if analysis.ppe_sampled:
                self._ppe_samples += 1

            pose_sampled = bool(
                getattr(analysis, "pose_sampled", False)
            )
            pose = getattr(analysis, "pose", None)

            if pose_sampled:
                self._pose_samples += 1

                if pose is not None:
                    self._pose_assigned += pose.assigned_count
                    self._pose_unassigned += pose.unassigned_count

            if analysis.ppe is None:
                return

            for trigger in analysis.ppe.depth_triggers:
                self._depth_trigger_attempts += 1
                if trigger.accepted:
                    self._depth_triggers_accepted += 1
                else:
                    self._depth_triggers_rejected += 1

                assessment = analysis.ppe.ppe.for_track(trigger.track_id)
                snapshot = assessment.snapshot

                self._write(
                    "PHASE3_PPE_TRIGGER "
                    f"EVENT_KEY={trigger.event_key} "
                    f"TRACK_ID={trigger.track_id} "
                    f"FRAME={analysis.ppe.ppe.frame_index} "
                    f"STATE={assessment.state.value} "
                    f"ACCEPTED={str(trigger.accepted).lower()} "
                    f"NO_HELMET_RATE={snapshot.head_no_helmet_rate * 100:.1f}% "
                    f"HELMET_RATE={snapshot.helmet_rate * 100:.1f}% "
                    f"UNKNOWN_RATE={snapshot.unknown_rate * 100:.1f}% "
                    f"STREAK_SEC={snapshot.current_streak_seconds:.3f}"
                )

                if self._reporter is not None:
                    frame = analysis.inference.frame

                    self._reporter.submit_event(
                        {
                            "eventKey": trigger.event_key,
                            "sourceId": frame.source_id,
                            "sessionId": frame.session_id,
                            "sourceType": frame.source_type.value,
                            "droneId": frame.drone_id,
                            "trackId": trigger.track_id,
                            "frameIndex": analysis.ppe.ppe.frame_index,
                            "capturedAt": frame.captured_at.isoformat(),
                            "ppeState": assessment.state.value,
                            "noHelmetRate": snapshot.head_no_helmet_rate,
                            "helmetRate": snapshot.helmet_rate,
                            "unknownRate": snapshot.unknown_rate,
                            "streakSeconds": snapshot.current_streak_seconds,
                        }
                    )

    def on_depth_result(self, result: DepthEnrichmentResult) -> None:
        measurement = result.measurement

        with self._lock:
            self._depth_results += 1
            self._write(
                "PHASE3_DEPTH_RESULT "
                f"EVENT_KEY={result.event_key} "
                f"TRACK_ID={result.track_id} "
                f"FRAME={result.frame_index} "
                f"TIME_SEC={result.event_time_sec:.3f} "
                f"EST_DEPTH_M={measurement.estimated_depth_m:.3f} "
                f"Q33_M={measurement.scene_q33_m:.3f} "
                f"Q66_M={measurement.scene_q66_m:.3f} "
                f"DEPTH_BUCKET={measurement.bucket.value} "
                f"ENRICHMENT_LATENCY_MS={result.enrichment_latency_ms:.2f}"
            )

            if self._reporter is not None:
                self._reporter.submit_depth(
                    result.event_key,
                    {
                        "estimatedDepthM": measurement.estimated_depth_m,
                        "sceneQ33M": measurement.scene_q33_m,
                        "sceneQ66M": measurement.scene_q66_m,
                        "depthBucket": measurement.bucket.value,
                        "enrichmentLatencyMs": result.enrichment_latency_ms,
                    },
                )

    def snapshot(self) -> Phase3ObservabilitySnapshot:
        with self._lock:
            return Phase3ObservabilitySnapshot(
                frames_analyzed=self._frames_analyzed,
                ppe_samples=self._ppe_samples,
                pose_samples=self._pose_samples,
                pose_assigned=self._pose_assigned,
                pose_unassigned=self._pose_unassigned,
                depth_trigger_attempts=self._depth_trigger_attempts,
                depth_triggers_accepted=self._depth_triggers_accepted,
                depth_triggers_rejected=self._depth_triggers_rejected,
                depth_results=self._depth_results,
            )

    def emit_summary(self) -> Phase3ObservabilitySnapshot:
        snapshot = self.snapshot()
        with self._lock:
            self._write(
                "PHASE3_SUMMARY "
                f"FRAMES_ANALYZED={snapshot.frames_analyzed} "
                f"PPE_SAMPLES={snapshot.ppe_samples} "
                f"POSE_SAMPLES={snapshot.pose_samples} "
                f"POSE_ASSIGNED={snapshot.pose_assigned} "
                f"POSE_UNASSIGNED={snapshot.pose_unassigned} "
                f"DEPTH_TRIGGER_ATTEMPTS={snapshot.depth_trigger_attempts} "
                f"DEPTH_TRIGGERS_ACCEPTED={snapshot.depth_triggers_accepted} "
                f"DEPTH_TRIGGERS_REJECTED={snapshot.depth_triggers_rejected} "
                f"DEPTH_RESULTS={snapshot.depth_results}"
            )
        return snapshot

    def _write(self, message: str) -> None:
        print(message, file=self._stream, flush=True)
