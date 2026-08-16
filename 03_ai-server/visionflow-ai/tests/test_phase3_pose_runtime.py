from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.inference.phase3_runtime import create_phase3_runtime


def _settings(
    *,
    pose_enabled: bool,
    pose_target_fps: float = 5.0,
):
    return SimpleNamespace(
        phase3_enabled=True,
        phase3_ppe_target_fps=10.0,
        phase3_pose_enabled=pose_enabled,
        phase3_pose_target_fps=pose_target_fps,
        phase3_depth_enabled=False,
    )


def test_pose_runtime_is_disabled_when_setting_is_false() -> None:
    runtime = create_phase3_runtime(
        settings=_settings(pose_enabled=False),
        source_fps=30.0,
    )

    assert runtime is not None
    assert runtime.pose_enabled is False
    assert runtime.pose_stride_frames is None
    assert runtime.effective_pose_fps == 0.0
    assert runtime.should_sample_pose(0) is False
    assert runtime.should_sample_pose(30) is False


def test_pose_runtime_computes_independent_5hz_stride_at_30fps() -> None:
    runtime = create_phase3_runtime(
        settings=_settings(pose_enabled=True),
        source_fps=30.0,
    )

    assert runtime is not None
    assert runtime.sample_stride_frames == 3
    assert runtime.effective_ppe_fps == pytest.approx(10.0)
    assert runtime.pose_stride_frames == 6
    assert runtime.effective_pose_fps == pytest.approx(5.0)
    assert runtime.pose_enabled is True


def test_pose_stride_never_exceeds_target_rate_for_2997fps() -> None:
    runtime = create_phase3_runtime(
        settings=_settings(pose_enabled=True),
        source_fps=29.97,
    )

    assert runtime is not None
    assert runtime.pose_stride_frames == 6
    assert runtime.effective_pose_fps == pytest.approx(4.995)
    assert runtime.effective_pose_fps <= 5.0


def test_pose_sampling_uses_zero_based_source_frame_index() -> None:
    runtime = create_phase3_runtime(
        settings=_settings(pose_enabled=True),
        source_fps=30.0,
    )

    assert runtime is not None
    assert runtime.should_sample_pose(0) is True
    assert runtime.should_sample_pose(1) is False
    assert runtime.should_sample_pose(5) is False
    assert runtime.should_sample_pose(6) is True
    assert runtime.should_sample_pose(11) is False
    assert runtime.should_sample_pose(12) is True


def test_pose_sampling_rejects_negative_frame_index() -> None:
    runtime = create_phase3_runtime(
        settings=_settings(pose_enabled=True),
        source_fps=30.0,
    )

    assert runtime is not None

    with pytest.raises(ValueError, match="source_frame_index"):
        runtime.should_sample_pose(-1)


def test_pose_target_can_have_different_cadence_from_ppe() -> None:
    runtime = create_phase3_runtime(
        settings=_settings(
            pose_enabled=True,
            pose_target_fps=4.0,
        ),
        source_fps=30.0,
    )

    assert runtime is not None
    assert runtime.sample_stride_frames == 3
    assert runtime.pose_stride_frames == 8
    assert runtime.effective_ppe_fps == pytest.approx(10.0)
    assert runtime.effective_pose_fps == pytest.approx(3.75)


def test_disabled_phase3_still_returns_no_runtime() -> None:
    settings = SimpleNamespace(
        phase3_enabled=False,
    )

    runtime = create_phase3_runtime(
        settings=settings,
        source_fps=30.0,
    )

    assert runtime is None
