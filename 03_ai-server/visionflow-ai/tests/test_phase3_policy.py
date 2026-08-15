from __future__ import annotations

import pytest

from app.inference.phase3_policy import (
    PpeComplianceState,
    PpeEvidence,
    PpePolicyConfig,
    evaluate_ppe_compliance,
)


def test_confirmed_no_helmet_uses_elapsed_frame_time() -> None:
    evidence = PpeEvidence(
        sample_count=10,
        helmet_count=0,
        head_count=10,
        head_no_helmet_count=10,
        unknown_count=0,
        source_fps=30.0,
        current_streak_start_frame=1,
        current_streak_end_frame=28,
        max_streak_start_frame=1,
        max_streak_end_frame=28,
    )

    decision = evaluate_ppe_compliance(evidence)

    assert decision.state is PpeComplianceState.CONFIRMED_NO_HELMET
    assert decision.current_streak_seconds == pytest.approx(0.9)
    assert decision.head_no_helmet_rate == pytest.approx(1.0)
    assert decision.helmet_rate == pytest.approx(0.0)


def test_safe_requires_dominant_helmet_evidence() -> None:
    evidence = PpeEvidence(
        sample_count=20,
        helmet_count=19,
        head_count=0,
        head_no_helmet_count=0,
        unknown_count=1,
        source_fps=30.0,
    )

    decision = evaluate_ppe_compliance(evidence)

    assert decision.state is PpeComplianceState.SAFE
    assert decision.helmet_rate == pytest.approx(0.95)
    assert decision.unknown_rate == pytest.approx(0.05)


def test_candidate_is_used_before_minimum_samples_are_available() -> None:
    evidence = PpeEvidence(
        sample_count=7,
        helmet_count=0,
        head_count=7,
        head_no_helmet_count=7,
        unknown_count=0,
        source_fps=30.0,
        current_streak_start_frame=1,
        current_streak_end_frame=19,
        max_streak_start_frame=1,
        max_streak_end_frame=19,
    )

    decision = evaluate_ppe_compliance(evidence)

    assert decision.state is PpeComplianceState.NO_HELMET_CANDIDATE
    assert decision.current_streak_seconds == pytest.approx(0.6)


def test_single_active_no_helmet_sample_is_candidate_even_at_zero_elapsed_time() -> None:
    evidence = PpeEvidence(
        sample_count=5,
        helmet_count=0,
        head_count=5,
        head_no_helmet_count=5,
        unknown_count=0,
        source_fps=30.0,
        current_streak_start_frame=20,
        current_streak_end_frame=20,
        max_streak_start_frame=1,
        max_streak_end_frame=10,
    )

    decision = evaluate_ppe_compliance(evidence)

    assert evidence.current_streak_active is True
    assert decision.current_streak_seconds == pytest.approx(0.0)
    assert decision.state is PpeComplianceState.NO_HELMET_CANDIDATE


def test_uncertain_track_stays_unknown() -> None:
    evidence = PpeEvidence(
        sample_count=20,
        helmet_count=1,
        head_count=6,
        head_no_helmet_count=6,
        unknown_count=13,
        source_fps=30.0,
        current_streak_start_frame=1,
        current_streak_end_frame=25,
        max_streak_start_frame=1,
        max_streak_end_frame=25,
    )

    decision = evaluate_ppe_compliance(evidence)

    assert decision.state is PpeComplianceState.UNKNOWN
    assert decision.head_no_helmet_rate == pytest.approx(0.30)
    assert decision.unknown_rate == pytest.approx(0.65)
    assert decision.current_streak_seconds == pytest.approx(0.8)


def test_previous_violation_does_not_confirm_after_current_streak_clears() -> None:
    evidence = PpeEvidence(
        sample_count=20,
        helmet_count=2,
        head_count=14,
        head_no_helmet_count=12,
        unknown_count=4,
        source_fps=30.0,
        current_streak_start_frame=0,
        current_streak_end_frame=0,
        max_streak_start_frame=1,
        max_streak_end_frame=31,
    )

    decision = evaluate_ppe_compliance(evidence)

    assert decision.state is PpeComplianceState.UNKNOWN
    assert decision.max_streak_seconds == pytest.approx(1.0)
    assert decision.current_streak_seconds == pytest.approx(0.0)


def test_policy_config_validates_rate_ranges() -> None:
    with pytest.raises(ValueError, match="min_no_helmet_rate"):
        PpePolicyConfig(min_no_helmet_rate=1.1).validate()
