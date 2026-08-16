from __future__ import annotations

from dataclasses import dataclass

from app.inference.phase3_policy import (
    PpeDecision,
    PpeEvidence,
    PpePolicyConfig,
    evaluate_ppe_compliance,
)


@dataclass(frozen=True, slots=True)
class TrackPpeSnapshot:
    track_id: int
    sample_count: int
    helmet_count: int
    head_count: int
    vest_count: int
    head_no_helmet_count: int
    unknown_count: int
    helmet_rate: float
    head_rate: float
    vest_rate: float
    head_no_helmet_rate: float
    unknown_rate: float
    current_streak_start_frame: int
    current_streak_end_frame: int
    current_streak_seconds: float
    max_streak_start_frame: int
    max_streak_end_frame: int
    max_streak_seconds: float
    last_sample_frame: int
    decision: PpeDecision


@dataclass(slots=True)
class _TrackPpeState:
    sample_count: int = 0
    helmet_count: int = 0
    head_count: int = 0
    vest_count: int = 0
    head_no_helmet_count: int = 0
    unknown_count: int = 0

    current_streak_start_frame: int = 0
    current_streak_end_frame: int = 0
    max_streak_start_frame: int = 0
    max_streak_end_frame: int = 0

    last_sample_frame: int = 0


class TrackPpeEvidenceAccumulator:
    def __init__(
        self,
        *,
        source_fps: float,
        sample_stride_frames: int,
        policy: PpePolicyConfig | None = None,
    ) -> None:
        if source_fps <= 0:
            raise ValueError("source_fps must be positive.")
        if sample_stride_frames <= 0:
            raise ValueError("sample_stride_frames must be positive.")

        self._source_fps = float(source_fps)
        self._sample_stride_frames = int(sample_stride_frames)
        self._policy = policy or PpePolicyConfig()
        self._policy.validate()
        self._states: dict[int, _TrackPpeState] = {}

    @property
    def source_fps(self) -> float:
        return self._source_fps

    @property
    def sample_stride_frames(self) -> int:
        return self._sample_stride_frames

    def observe(
        self,
        *,
        track_id: int,
        frame_index: int,
        has_helmet: bool,
        has_head: bool,
        has_vest: bool,
    ) -> TrackPpeSnapshot:
        if track_id <= 0:
            raise ValueError("track_id must be positive.")
        if frame_index <= 0:
            raise ValueError("frame_index must be positive.")

        state = self._states.setdefault(track_id, _TrackPpeState())

        if state.last_sample_frame and frame_index <= state.last_sample_frame:
            raise ValueError(
                "frame_index must increase monotonically for each track."
            )

        expected_frame = (
            state.last_sample_frame + self._sample_stride_frames
            if state.last_sample_frame
            else frame_index
        )
        contiguous_sample = (
            state.last_sample_frame == 0
            or frame_index == expected_frame
        )

        if not contiguous_sample:
            self._clear_current_streak(state)

        state.last_sample_frame = frame_index
        state.sample_count += 1
        state.helmet_count += int(has_helmet)
        state.head_count += int(has_head)
        state.vest_count += int(has_vest)

        head_no_helmet = has_head and not has_helmet
        if head_no_helmet:
            state.head_no_helmet_count += 1
            self._extend_current_streak(state, frame_index)
            self._update_max_streak(state)
        else:
            self._clear_current_streak(state)

        if not has_helmet and not has_head:
            state.unknown_count += 1

        return self.snapshot(track_id)

    def snapshot(self, track_id: int) -> TrackPpeSnapshot:
        state = self._states.get(track_id)
        if state is None:
            raise KeyError(f"Unknown track_id: {track_id}")

        evidence = self._build_evidence(state)
        decision = evaluate_ppe_compliance(evidence, self._policy)

        sample_count = state.sample_count
        return TrackPpeSnapshot(
            track_id=track_id,
            sample_count=sample_count,
            helmet_count=state.helmet_count,
            head_count=state.head_count,
            vest_count=state.vest_count,
            head_no_helmet_count=state.head_no_helmet_count,
            unknown_count=state.unknown_count,
            helmet_rate=_rate(state.helmet_count, sample_count),
            head_rate=_rate(state.head_count, sample_count),
            vest_rate=_rate(state.vest_count, sample_count),
            head_no_helmet_rate=_rate(
                state.head_no_helmet_count,
                sample_count,
            ),
            unknown_rate=_rate(state.unknown_count, sample_count),
            current_streak_start_frame=state.current_streak_start_frame,
            current_streak_end_frame=state.current_streak_end_frame,
            current_streak_seconds=evidence.current_streak_seconds,
            max_streak_start_frame=state.max_streak_start_frame,
            max_streak_end_frame=state.max_streak_end_frame,
            max_streak_seconds=evidence.max_streak_seconds,
            last_sample_frame=state.last_sample_frame,
            decision=decision,
        )

    def snapshots(self) -> tuple[TrackPpeSnapshot, ...]:
        return tuple(
            self.snapshot(track_id)
            for track_id in sorted(self._states)
        )

    def remove(self, track_id: int) -> bool:
        return self._states.pop(track_id, None) is not None

    def clear(self) -> None:
        self._states.clear()

    def _build_evidence(self, state: _TrackPpeState) -> PpeEvidence:
        return PpeEvidence(
            sample_count=state.sample_count,
            helmet_count=state.helmet_count,
            head_count=state.head_count,
            head_no_helmet_count=state.head_no_helmet_count,
            unknown_count=state.unknown_count,
            source_fps=self._source_fps,
            current_streak_start_frame=state.current_streak_start_frame,
            current_streak_end_frame=state.current_streak_end_frame,
            max_streak_start_frame=state.max_streak_start_frame,
            max_streak_end_frame=state.max_streak_end_frame,
        )

    @staticmethod
    def _extend_current_streak(
        state: _TrackPpeState,
        frame_index: int,
    ) -> None:
        if state.current_streak_start_frame == 0:
            state.current_streak_start_frame = frame_index

        state.current_streak_end_frame = frame_index

    @staticmethod
    def _clear_current_streak(state: _TrackPpeState) -> None:
        state.current_streak_start_frame = 0
        state.current_streak_end_frame = 0

    def _update_max_streak(self, state: _TrackPpeState) -> None:
        current_span = _frame_span(
            state.current_streak_start_frame,
            state.current_streak_end_frame,
        )
        max_span = _frame_span(
            state.max_streak_start_frame,
            state.max_streak_end_frame,
        )

        if current_span > max_span:
            state.max_streak_start_frame = state.current_streak_start_frame
            state.max_streak_end_frame = state.current_streak_end_frame


def _rate(count: int, sample_count: int) -> float:
    if sample_count <= 0:
        return 0.0
    return count / sample_count


def _frame_span(start_frame: int, end_frame: int) -> int:
    if start_frame <= 0 or end_frame < start_frame:
        return 0
    return end_frame - start_frame
