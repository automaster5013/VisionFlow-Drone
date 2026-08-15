from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PpeComplianceState(StrEnum):
    SAFE = "SAFE"
    UNKNOWN = "UNKNOWN"
    NO_HELMET_CANDIDATE = "NO_HELMET_CANDIDATE"
    CONFIRMED_NO_HELMET = "CONFIRMED_NO_HELMET"


@dataclass(frozen=True, slots=True)
class PpePolicyConfig:
    min_samples: int = 10
    min_no_helmet_rate: float = 0.60
    max_helmet_rate: float = 0.20
    max_unknown_rate: float = 0.40
    min_streak_seconds: float = 0.75

    safe_min_helmet_rate: float = 0.80
    safe_max_no_helmet_rate: float = 0.05
    safe_max_unknown_rate: float = 0.20

    def validate(self) -> None:
        if self.min_samples <= 0:
            raise ValueError("min_samples must be positive.")

        for name, value in (
            ("min_no_helmet_rate", self.min_no_helmet_rate),
            ("max_helmet_rate", self.max_helmet_rate),
            ("max_unknown_rate", self.max_unknown_rate),
            ("safe_min_helmet_rate", self.safe_min_helmet_rate),
            ("safe_max_no_helmet_rate", self.safe_max_no_helmet_rate),
            ("safe_max_unknown_rate", self.safe_max_unknown_rate),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in the range [0, 1].")

        if self.min_streak_seconds < 0:
            raise ValueError("min_streak_seconds must be non-negative.")


@dataclass(frozen=True, slots=True)
class PpeEvidence:
    sample_count: int
    helmet_count: int
    head_count: int
    head_no_helmet_count: int
    unknown_count: int
    source_fps: float

    current_streak_start_frame: int = 0
    current_streak_end_frame: int = 0
    max_streak_start_frame: int = 0
    max_streak_end_frame: int = 0

    def validate(self) -> None:
        if self.sample_count < 0:
            raise ValueError("sample_count must be non-negative.")
        if self.source_fps <= 0:
            raise ValueError("source_fps must be positive.")

        counts = {
            "helmet_count": self.helmet_count,
            "head_count": self.head_count,
            "head_no_helmet_count": self.head_no_helmet_count,
            "unknown_count": self.unknown_count,
        }
        for name, value in counts.items():
            if value < 0:
                raise ValueError(f"{name} must be non-negative.")
            if value > self.sample_count:
                raise ValueError(f"{name} cannot exceed sample_count.")

        if self.head_no_helmet_count > self.head_count:
            raise ValueError("head_no_helmet_count cannot exceed head_count.")

        _validate_streak(
            self.current_streak_start_frame,
            self.current_streak_end_frame,
            "current",
        )
        _validate_streak(
            self.max_streak_start_frame,
            self.max_streak_end_frame,
            "max",
        )

    @property
    def helmet_rate(self) -> float:
        return _rate(self.helmet_count, self.sample_count)

    @property
    def head_rate(self) -> float:
        return _rate(self.head_count, self.sample_count)

    @property
    def head_no_helmet_rate(self) -> float:
        return _rate(self.head_no_helmet_count, self.sample_count)

    @property
    def unknown_rate(self) -> float:
        return _rate(self.unknown_count, self.sample_count)

    @property
    def current_streak_active(self) -> bool:
        return (
            self.current_streak_start_frame > 0
            and self.current_streak_end_frame >= self.current_streak_start_frame
        )

    @property
    def current_streak_seconds(self) -> float:
        return _streak_seconds(
            self.current_streak_start_frame,
            self.current_streak_end_frame,
            self.source_fps,
        )

    @property
    def max_streak_seconds(self) -> float:
        return _streak_seconds(
            self.max_streak_start_frame,
            self.max_streak_end_frame,
            self.source_fps,
        )


@dataclass(frozen=True, slots=True)
class PpeDecision:
    state: PpeComplianceState
    sample_count: int
    helmet_rate: float
    head_rate: float
    head_no_helmet_rate: float
    unknown_rate: float
    current_streak_seconds: float
    max_streak_seconds: float
    reason: str


def evaluate_ppe_compliance(
    evidence: PpeEvidence,
    config: PpePolicyConfig | None = None,
) -> PpeDecision:
    policy = config or PpePolicyConfig()
    policy.validate()
    evidence.validate()

    if evidence.sample_count == 0:
        return _decision(
            PpeComplianceState.UNKNOWN,
            evidence,
            "No PPE samples are available.",
        )

    confirmed = (
        evidence.sample_count >= policy.min_samples
        and evidence.head_no_helmet_rate >= policy.min_no_helmet_rate
        and evidence.helmet_rate <= policy.max_helmet_rate
        and evidence.unknown_rate <= policy.max_unknown_rate
        and evidence.current_streak_seconds >= policy.min_streak_seconds
    )
    if confirmed:
        return _decision(
            PpeComplianceState.CONFIRMED_NO_HELMET,
            evidence,
            "Sustained head-without-helmet evidence satisfies policy thresholds.",
        )

    safe = (
        evidence.sample_count >= policy.min_samples
        and evidence.helmet_rate >= policy.safe_min_helmet_rate
        and evidence.head_no_helmet_rate <= policy.safe_max_no_helmet_rate
        and evidence.unknown_rate <= policy.safe_max_unknown_rate
        and not evidence.current_streak_active
    )
    if safe:
        return _decision(
            PpeComplianceState.SAFE,
            evidence,
            "Helmet evidence is dominant and no active violation streak exists.",
        )

    if (
        evidence.sample_count < policy.min_samples
        and evidence.current_streak_active
        and evidence.head_no_helmet_count > 0
    ):
        return _decision(
            PpeComplianceState.NO_HELMET_CANDIDATE,
            evidence,
            "Active head-without-helmet evidence exists but minimum samples are not met.",
        )

    return _decision(
        PpeComplianceState.UNKNOWN,
        evidence,
        "Evidence is insufficient or conflicting for a safe or violation decision.",
    )


def _decision(
    state: PpeComplianceState,
    evidence: PpeEvidence,
    reason: str,
) -> PpeDecision:
    return PpeDecision(
        state=state,
        sample_count=evidence.sample_count,
        helmet_rate=evidence.helmet_rate,
        head_rate=evidence.head_rate,
        head_no_helmet_rate=evidence.head_no_helmet_rate,
        unknown_rate=evidence.unknown_rate,
        current_streak_seconds=evidence.current_streak_seconds,
        max_streak_seconds=evidence.max_streak_seconds,
        reason=reason,
    )


def _rate(count: int, sample_count: int) -> float:
    if sample_count <= 0:
        return 0.0
    return count / sample_count


def _validate_streak(start_frame: int, end_frame: int, name: str) -> None:
    if start_frame < 0 or end_frame < 0:
        raise ValueError(f"{name} streak frame indexes must be non-negative.")
    if start_frame == 0 and end_frame == 0:
        return
    if start_frame <= 0 or end_frame < start_frame:
        raise ValueError(f"{name} streak frame range is invalid.")


def _streak_seconds(start_frame: int, end_frame: int, source_fps: float) -> float:
    if start_frame <= 0 or end_frame < start_frame:
        return 0.0
    return (end_frame - start_frame) / source_fps
