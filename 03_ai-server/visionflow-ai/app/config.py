from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from app.domain import SmartphoneInputMode, SnapshotPolicy, VideoSourceType


def _read_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def _read_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None else int(value)


def _read_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value is None else float(value)


def _read_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)

    if value is None:
        return default

    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    source_type: VideoSourceType
    source_id: str
    session_id: str
    drone_id: int
    dummy_video_path: Path
    loop_video: bool
    realtime_playback: bool
    smartphone_input_mode: SmartphoneInputMode
    smartphone_stream_url: str
    smartphone_reconnect: bool
    smartphone_reconnect_delay_seconds: float
    smartphone_max_reconnect_attempts: int
    smartphone_open_timeout_ms: int
    smartphone_read_timeout_ms: int
    browser_upload_fps: float
    browser_upload_queue_capacity: int
    browser_upload_max_payload_bytes: int
    model_profile: str
    model_path: str
    model_manifest_path: str
    model_profiles_path: str
    compare_baseline_model_path: str
    compare_candidate_model_path: str
    compare_candidate_manifest_path: str
    require_cuda: bool
    require_local_model: bool
    confidence: float
    iou: float
    image_size: int
    device: str
    phase3_enabled: bool
    phase3_ppe_model_path: str
    phase3_ppe_target_fps: float
    phase3_pose_enabled: bool
    phase3_pose_model_path: str
    phase3_pose_target_fps: float
    phase3_segmentation_enabled: bool
    phase3_segmentation_model_path: str
    phase3_segmentation_target_fps: float
    phase3_depth_enabled: bool
    phase3_depth_model_path: str
    phase3_depth_image_size: int
    phase3_depth_queue_capacity: int
    phase3_report_events: bool
    backend_phase3_event_url: str
    save_annotated_video: bool
    output_video_path: Path
    show_preview: bool
    max_frames: int
    report_events: bool
    backend_event_url: str
    report_timeout_seconds: float
    report_max_retries: int
    report_queue_capacity: int
    event_min_consecutive_frames: int
    event_cooldown_seconds: float
    snapshot_policy: SnapshotPolicy
    snapshot_jpeg_quality: int
    stream_enabled: bool
    stream_host: str
    stream_port: int
    stream_jpeg_quality: int
    stream_allowed_origins: tuple[str, ...]
    ai_internal_security_enabled: bool
    ai_internal_key: str
    dji_bridge_key: str
    performance_warning_p95_ms: float
    performance_critical_p95_ms: float
    performance_warning_processing_ratio: float
    performance_critical_processing_ratio: float
    performance_warning_drop_rate_pct: float
    performance_critical_drop_rate_pct: float
    performance_warning_queue_utilization_pct: float
    performance_critical_queue_utilization_pct: float
    performance_stale_after_seconds: float
    performance_min_sample_count: int

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv()

        source_type = VideoSourceType(
            os.getenv("AI_SOURCE_TYPE", VideoSourceType.DUMMY_VIDEO.value)
        )

        settings = cls(
            source_type=source_type,
            source_id=os.getenv("AI_SOURCE_ID", "digital-twin-camera-001"),
            session_id=os.getenv("AI_SESSION_ID", str(uuid4())),
            drone_id=_read_int("AI_DRONE_ID", 1),
            dummy_video_path=Path(os.getenv("AI_DUMMY_VIDEO_PATH", "data/dummy/sample.mp4")),
            loop_video=_read_bool("AI_LOOP_VIDEO", True),
            realtime_playback=_read_bool("AI_REALTIME_PLAYBACK", True),
            smartphone_input_mode=SmartphoneInputMode(
                os.getenv(
                    "AI_SMARTPHONE_INPUT_MODE",
                    SmartphoneInputMode.STREAM_URL.value,
                )
            ),
            smartphone_stream_url=os.getenv("AI_SMARTPHONE_STREAM_URL", ""),
            smartphone_reconnect=_read_bool("AI_SMARTPHONE_RECONNECT", True),
            smartphone_reconnect_delay_seconds=_read_float(
                "AI_SMARTPHONE_RECONNECT_DELAY_SECONDS",
                2.0,
            ),
            smartphone_max_reconnect_attempts=_read_int(
                "AI_SMARTPHONE_MAX_RECONNECT_ATTEMPTS",
                10,
            ),
            smartphone_open_timeout_ms=_read_int(
                "AI_SMARTPHONE_OPEN_TIMEOUT_MS",
                5_000,
            ),
            smartphone_read_timeout_ms=_read_int(
                "AI_SMARTPHONE_READ_TIMEOUT_MS",
                5_000,
            ),
            browser_upload_fps=_read_float("AI_BROWSER_UPLOAD_FPS", 5.0),
            browser_upload_queue_capacity=_read_int(
                "AI_BROWSER_UPLOAD_QUEUE_CAPACITY",
                3,
            ),
            browser_upload_max_payload_bytes=_read_int(
                "AI_BROWSER_UPLOAD_MAX_PAYLOAD_BYTES",
                2_000_000,
            ),
            model_profile=os.getenv("AI_MODEL_PROFILE", "yolo26n-cpu"),
            model_path=os.getenv("AI_MODEL_PATH", "yolo26n.pt"),
            model_manifest_path=os.getenv("AI_MODEL_MANIFEST_PATH", ""),
            model_profiles_path=os.getenv(
                "AI_MODEL_PROFILES_PATH",
                "config/model-profiles-v1.json",
            ),
            compare_baseline_model_path=os.getenv(
                "AI_COMPARE_BASELINE_MODEL_PATH",
                "models/yolo26m.pt",
            ),
            compare_candidate_model_path=os.getenv(
                "AI_COMPARE_CANDIDATE_MODEL_PATH",
                "models/yolo26m-visdrone-s2-best.pt",
            ),
            compare_candidate_manifest_path=os.getenv(
                "AI_COMPARE_CANDIDATE_MANIFEST_PATH",
                "models/manifests/yolo26m-visdrone-s2-best.manifest.json",
            ),
            require_cuda=_read_bool("AI_REQUIRE_CUDA", False),
            require_local_model=_read_bool("AI_REQUIRE_LOCAL_MODEL", False),
            confidence=_read_float("AI_CONFIDENCE", 0.35),
            iou=_read_float("AI_IOU", 0.70),
            image_size=_read_int("AI_IMAGE_SIZE", 640),
            device=os.getenv("AI_DEVICE", "cpu"),
            phase3_enabled=_read_bool("AI_PHASE3_ENABLED", False),
            phase3_ppe_model_path=os.getenv(
                "AI_PHASE3_PPE_MODEL_PATH",
                "/app/models/ppe-yolo26m-best.pt",
            ),
            phase3_ppe_target_fps=_read_float(
                "AI_PHASE3_PPE_TARGET_FPS",
                10.0,
            ),
            phase3_pose_enabled=_read_bool(
                "AI_PHASE3_POSE_ENABLED",
                False,
            ),
            phase3_pose_model_path=os.getenv(
                "AI_PHASE3_POSE_MODEL_PATH",
                "/app/models/yolo26m-pose.pt",
            ),
            phase3_pose_target_fps=_read_float(
                "AI_PHASE3_POSE_TARGET_FPS",
                5.0,
            ),
            phase3_segmentation_enabled=_read_bool(
                "AI_PHASE3_SEGMENTATION_ENABLED",
                False,
            ),
            phase3_segmentation_model_path=os.getenv(
                "AI_PHASE3_SEGMENTATION_MODEL_PATH",
                "/app/models/yolo26m-seg.pt",
            ),
            phase3_segmentation_target_fps=_read_float(
                "AI_PHASE3_SEGMENTATION_TARGET_FPS",
                5.0,
            ),
            phase3_depth_enabled=_read_bool(
                "AI_PHASE3_DEPTH_ENABLED",
                True,
            ),
            phase3_depth_model_path=os.getenv(
                "AI_PHASE3_DEPTH_MODEL_PATH",
                "/app/models/yolo26m-depth.pt",
            ),
            phase3_depth_image_size=_read_int(
                "AI_PHASE3_DEPTH_IMAGE_SIZE",
                768,
            ),
            phase3_depth_queue_capacity=_read_int(
                "AI_PHASE3_DEPTH_QUEUE_CAPACITY",
                4,
            ),
            phase3_report_events=_read_bool(
                "AI_PHASE3_REPORT_EVENTS",
                False,
            ),
            backend_phase3_event_url=os.getenv(
                "AI_BACKEND_PHASE3_EVENT_URL",
                "http://localhost:8080/api/ai/phase3/events",
            ),
            save_annotated_video=_read_bool("AI_SAVE_ANNOTATED_VIDEO", True),
            output_video_path=Path(os.getenv("AI_OUTPUT_VIDEO_PATH", "output/annotated.mp4")),
            show_preview=_read_bool("AI_SHOW_PREVIEW", False),
            max_frames=_read_int("AI_MAX_FRAMES", 0),
            report_events=_read_bool("AI_REPORT_EVENTS", True),
            backend_event_url=os.getenv(
                "AI_BACKEND_EVENT_URL",
                "http://localhost:8080/api/ai/events",
            ),
            report_timeout_seconds=_read_float(
                "AI_REPORT_TIMEOUT_SECONDS",
                3.0,
            ),
            report_max_retries=_read_int("AI_REPORT_MAX_RETRIES", 3),
            report_queue_capacity=_read_int(
                "AI_REPORT_QUEUE_CAPACITY",
                200,
            ),
            event_min_consecutive_frames=_read_int(
                "AI_EVENT_MIN_CONSECUTIVE_FRAMES",
                5,
            ),
            event_cooldown_seconds=_read_float(
                "AI_EVENT_COOLDOWN_SECONDS",
                10.0,
            ),
            snapshot_policy=SnapshotPolicy(
                os.getenv(
                    "AI_SNAPSHOT_POLICY",
                    SnapshotPolicy.OFF.value,
                ).strip().upper()
            ),
            snapshot_jpeg_quality=_read_int(
                "AI_SNAPSHOT_JPEG_QUALITY",
                85,
            ),
            stream_enabled=_read_bool("AI_STREAM_ENABLED", True),
            stream_host=os.getenv("AI_STREAM_HOST", "127.0.0.1"),
            stream_port=_read_int("AI_STREAM_PORT", 8000),
            stream_jpeg_quality=_read_int("AI_STREAM_JPEG_QUALITY", 80),
            stream_allowed_origins=_read_csv(
                "AI_STREAM_ALLOWED_ORIGINS",
                ("http://localhost:3000", "http://127.0.0.1:3000"),
            ),
            ai_internal_security_enabled=_read_bool(
                "VISIONFLOW_AI_INTERNAL_SECURITY_ENABLED",
                True,
            ),
            ai_internal_key=os.getenv("VISIONFLOW_AI_INTERNAL_KEY", "").strip(),
            dji_bridge_key=os.getenv(
                "VISIONFLOW_DJI_BRIDGE_KEY", ""
            ).strip(),
            performance_warning_p95_ms=_read_float(
                "AI_PERFORMANCE_WARNING_P95_MS",
                250.0,
            ),
            performance_critical_p95_ms=_read_float(
                "AI_PERFORMANCE_CRITICAL_P95_MS",
                500.0,
            ),
            performance_warning_processing_ratio=_read_float(
                "AI_PERFORMANCE_WARNING_PROCESSING_RATIO",
                0.90,
            ),
            performance_critical_processing_ratio=_read_float(
                "AI_PERFORMANCE_CRITICAL_PROCESSING_RATIO",
                0.70,
            ),
            performance_warning_drop_rate_pct=_read_float(
                "AI_PERFORMANCE_WARNING_DROP_RATE_PCT",
                1.0,
            ),
            performance_critical_drop_rate_pct=_read_float(
                "AI_PERFORMANCE_CRITICAL_DROP_RATE_PCT",
                5.0,
            ),
            performance_warning_queue_utilization_pct=_read_float(
                "AI_PERFORMANCE_WARNING_QUEUE_UTILIZATION_PCT",
                67.0,
            ),
            performance_critical_queue_utilization_pct=_read_float(
                "AI_PERFORMANCE_CRITICAL_QUEUE_UTILIZATION_PCT",
                100.0,
            ),
            performance_stale_after_seconds=_read_float(
                "AI_PERFORMANCE_STALE_AFTER_SECONDS",
                5.0,
            ),
            performance_min_sample_count=_read_int(
                "AI_PERFORMANCE_MIN_SAMPLE_COUNT",
                5,
            ),
        )

        settings.validate()
        return settings

    def validate(self) -> None:
        if self.drone_id <= 0:
            raise ValueError("AI_DRONE_ID는 1 이상이어야 합니다.")

        if not 0.0 < self.confidence <= 1.0:
            raise ValueError("AI_CONFIDENCE는 0 초과 1 이하여야 합니다.")

        if not 0.0 < self.iou <= 1.0:
            raise ValueError("AI_IOU는 0 초과 1 이하여야 합니다.")

        if self.image_size <= 0:
            raise ValueError("AI_IMAGE_SIZE는 양수여야 합니다.")

        if not self.model_profile.strip():
            raise ValueError("AI_MODEL_PROFILE은 비어 있을 수 없습니다.")

        is_compare = self.model_profile.strip() == "DETERMINISTIC_COMPARE"

        if not is_compare and not self.model_path.strip():
            raise ValueError("AI_MODEL_PATH는 비어 있을 수 없습니다.")

        standard_profiles = {
            "GENERAL_LIVE",
            "AERIAL_SMALL_OBJECT_LIVE",
            "DETERMINISTIC_COMPARE",
        }
        if (
            self.model_profile.strip() in standard_profiles
            and not self.model_profiles_path.strip()
        ):
            raise ValueError("AI_MODEL_PROFILES_PATH는 비어 있을 수 없습니다.")

        if (
            self.model_profile.strip() == "AERIAL_SMALL_OBJECT_LIVE"
            and not self.model_manifest_path.strip()
        ):
            raise ValueError(
                "AERIAL_SMALL_OBJECT_LIVE에는 AI_MODEL_MANIFEST_PATH가 필요합니다."
            )

        if is_compare:
            compare_paths = {
                "AI_COMPARE_BASELINE_MODEL_PATH": self.compare_baseline_model_path,
                "AI_COMPARE_CANDIDATE_MODEL_PATH": self.compare_candidate_model_path,
                "AI_COMPARE_CANDIDATE_MANIFEST_PATH": (
                    self.compare_candidate_manifest_path
                ),
            }
            for name, path in compare_paths.items():
                if not path.strip():
                    raise ValueError(f"{name}는 비어 있을 수 없습니다.")

            if self.source_type is not VideoSourceType.DUMMY_VIDEO:
                raise ValueError(
                    "DETERMINISTIC_COMPARE는 AI_SOURCE_TYPE=DUMMY_VIDEO만 허용합니다."
                )
            if self.phase3_enabled:
                raise ValueError(
                    "DETERMINISTIC_COMPARE에서는 AI_PHASE3_ENABLED=false여야 합니다."
                )
            if self.report_events:
                raise ValueError(
                    "DETERMINISTIC_COMPARE에서는 AI_REPORT_EVENTS=false여야 합니다."
                )
            if self.snapshot_policy is not SnapshotPolicy.OFF:
                raise ValueError(
                    "DETERMINISTIC_COMPARE에서는 AI_SNAPSHOT_POLICY=OFF여야 합니다."
                )

        if self.require_cuda and self.device.strip().lower() in {"", "cpu", "mps"}:
            raise ValueError(
                "AI_REQUIRE_CUDA=true이면 AI_DEVICE에 "
                "0, cuda 또는 cuda:0을 지정해야 합니다."
            )

        if self.phase3_enabled:
            if not self.phase3_ppe_model_path.strip():
                raise ValueError(
                    "AI_PHASE3_PPE_MODEL_PATH는 비어 있을 수 없습니다."
                )

            if self.phase3_ppe_target_fps <= 0:
                raise ValueError(
                    "AI_PHASE3_PPE_TARGET_FPS는 양수여야 합니다."
                )

            if self.phase3_pose_enabled:
                if not self.phase3_pose_model_path.strip():
                    raise ValueError(
                        "AI_PHASE3_POSE_MODEL_PATH must not be blank."
                    )

                if self.phase3_pose_target_fps <= 0:
                    raise ValueError(
                        "AI_PHASE3_POSE_TARGET_FPS must be positive."
                    )

            if self.phase3_segmentation_enabled:
                if not self.phase3_segmentation_model_path.strip():
                    raise ValueError(
                        "AI_PHASE3_SEGMENTATION_MODEL_PATH must not be blank."
                    )

                if self.phase3_segmentation_target_fps <= 0:
                    raise ValueError(
                        "AI_PHASE3_SEGMENTATION_TARGET_FPS must be positive."
                    )

            if self.phase3_depth_enabled:
                if not self.phase3_depth_model_path.strip():
                    raise ValueError(
                        "AI_PHASE3_DEPTH_MODEL_PATH는 비어 있을 수 없습니다."
                    )

                if self.phase3_depth_image_size <= 0:
                    raise ValueError(
                        "AI_PHASE3_DEPTH_IMAGE_SIZE는 양수여야 합니다."
                    )

                if self.phase3_depth_queue_capacity <= 0:
                    raise ValueError(
                        "AI_PHASE3_DEPTH_QUEUE_CAPACITY는 양수여야 합니다."
                    )

        if self.max_frames < 0:
            raise ValueError("AI_MAX_FRAMES는 0 이상이어야 합니다.")

        if not self.session_id or len(self.session_id) > 36:
            raise ValueError("AI_SESSION_ID는 1~36자여야 합니다.")

        if self.report_timeout_seconds <= 0:
            raise ValueError("AI_REPORT_TIMEOUT_SECONDS는 양수여야 합니다.")

        if self.report_max_retries < 0:
            raise ValueError("AI_REPORT_MAX_RETRIES는 0 이상이어야 합니다.")

        if self.report_queue_capacity <= 0:
            raise ValueError("AI_REPORT_QUEUE_CAPACITY는 양수여야 합니다.")

        if self.event_min_consecutive_frames <= 0:
            raise ValueError(
                "AI_EVENT_MIN_CONSECUTIVE_FRAMES는 1 이상이어야 합니다."
            )

        if self.event_cooldown_seconds < 0:
            raise ValueError(
                "AI_EVENT_COOLDOWN_SECONDS는 0 이상이어야 합니다."
            )

        if not 1 <= self.snapshot_jpeg_quality <= 100:
            raise ValueError("AI_SNAPSHOT_JPEG_QUALITY는 1~100 범위여야 합니다.")

        if not self.stream_host.strip():
            raise ValueError("AI_STREAM_HOST는 비어 있을 수 없습니다.")

        if not 1 <= self.stream_port <= 65_535:
            raise ValueError("AI_STREAM_PORT는 1~65535 범위여야 합니다.")

        if not 1 <= self.stream_jpeg_quality <= 100:
            raise ValueError("AI_STREAM_JPEG_QUALITY는 1~100 범위여야 합니다.")

        if self.stream_enabled and not self.stream_allowed_origins:
            raise ValueError("AI_STREAM_ALLOWED_ORIGINS에는 하나 이상의 주소가 필요합니다.")

        if self.ai_internal_security_enabled and len(self.ai_internal_key) < 32:
            raise ValueError(
                "VISIONFLOW_AI_INTERNAL_SECURITY_ENABLED=true이면 "
                "VISIONFLOW_AI_INTERNAL_KEY를 32자 이상으로 설정해야 합니다."
            )

        if self.dji_bridge_key and len(self.dji_bridge_key) < 32:
            raise ValueError(
                "VISIONFLOW_DJI_BRIDGE_KEY는 설정할 경우 "
                "32자 이상이어야 합니다."
            )

        if (
            self.dji_bridge_key
            and self.ai_internal_key
            and self.dji_bridge_key == self.ai_internal_key
        ):
            raise ValueError(
                "VISIONFLOW_DJI_BRIDGE_KEY와 VISIONFLOW_AI_INTERNAL_KEY는 서로 달라야 합니다."
            )

        if not (
            0
            < self.performance_warning_p95_ms
            < self.performance_critical_p95_ms
        ):
            raise ValueError(
                "AI 성능 P95 임계치는 0 < WARNING < CRITICAL이어야 합니다."
            )

        if not (
            0
            < self.performance_critical_processing_ratio
            < self.performance_warning_processing_ratio
            <= 1
        ):
            raise ValueError(
                "AI 처리율 임계치는 0 < CRITICAL < WARNING <= 1이어야 합니다."
            )

        if not (
            0
            <= self.performance_warning_drop_rate_pct
            < self.performance_critical_drop_rate_pct
            <= 100
        ):
            raise ValueError(
                "AI 드롭률 임계치는 0 <= WARNING < CRITICAL <= 100이어야 합니다."
            )

        if not (
            0
            <= self.performance_warning_queue_utilization_pct
            < self.performance_critical_queue_utilization_pct
            <= 100
        ):
            raise ValueError(
                "AI 큐 사용률 임계치는 0 <= WARNING < CRITICAL <= 100이어야 합니다."
            )

        if self.performance_stale_after_seconds <= 0:
            raise ValueError("AI 입력 대기 판정 시간은 양수여야 합니다.")

        if self.performance_min_sample_count <= 0:
            raise ValueError("AI 성능 판정 최소 표본 수는 양수여야 합니다.")

        if self.smartphone_reconnect_delay_seconds < 0:
            raise ValueError("AI_SMARTPHONE_RECONNECT_DELAY_SECONDS는 0 이상이어야 합니다.")

        if self.smartphone_max_reconnect_attempts < 0:
            raise ValueError("AI_SMARTPHONE_MAX_RECONNECT_ATTEMPTS는 0 이상이어야 합니다.")

        if self.smartphone_open_timeout_ms <= 0:
            raise ValueError("AI_SMARTPHONE_OPEN_TIMEOUT_MS는 양수여야 합니다.")

        if self.smartphone_read_timeout_ms <= 0:
            raise ValueError("AI_SMARTPHONE_READ_TIMEOUT_MS는 양수여야 합니다.")

        if self.browser_upload_fps <= 0:
            raise ValueError("AI_BROWSER_UPLOAD_FPS는 양수여야 합니다.")

        if self.browser_upload_queue_capacity <= 0:
            raise ValueError("AI_BROWSER_UPLOAD_QUEUE_CAPACITY는 양수여야 합니다.")

        if self.browser_upload_max_payload_bytes <= 0:
            raise ValueError("AI_BROWSER_UPLOAD_MAX_PAYLOAD_BYTES는 양수여야 합니다.")

        if (
            self.source_type is VideoSourceType.SMARTPHONE_LIVE
            and self.smartphone_input_mode is SmartphoneInputMode.STREAM_URL
            and not self.smartphone_stream_url.strip()
        ):
            raise ValueError("SMARTPHONE_LIVE 입력에는 AI_SMARTPHONE_STREAM_URL이 필요합니다.")

        if (
            self.source_type is VideoSourceType.SMARTPHONE_LIVE
            and self.smartphone_input_mode is SmartphoneInputMode.BROWSER_UPLOAD
            and not self.stream_enabled
        ):
            raise ValueError("BROWSER_UPLOAD 입력에는 AI_STREAM_ENABLED=true가 필요합니다.")

        if self.source_type is VideoSourceType.DUMMY_VIDEO and not self.dummy_video_path.is_file():
            raise FileNotFoundError(
                f"더미 영상 파일을 찾을 수 없습니다: {self.dummy_video_path.resolve()}"
            )
