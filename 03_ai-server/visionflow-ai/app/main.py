from __future__ import annotations

from app.config import Settings
from app.domain import SmartphoneInputMode, VideoSourceType
from app.inference import YoloDetector
from app.inference.phase3_frame import (
    Phase3FrameAnalyzer,
    create_phase3_frame_analyzer,
)
from app.inference.phase3_observability import Phase3ConsoleObserver
from app.inference.phase3_runtime import (
    Phase3Runtime,
    create_phase3_runtime,
)
from app.metrics import InferencePerformanceMonitor, PerformanceThresholds
from app.pipeline import InferencePipeline
from app.reporting import SpringEventReporter
from app.sources import (
    BrowserUploadSource,
    DummyVideoSource,
    SmartphoneLiveSource,
    VideoSource,
    create_dji_live_source,
)
from app.streaming import AnalysisStreamServer, AnnotatedFrameHub
from app.phase3_reporting import Phase3EventReporter, Phase3EventReporterLike


def create_source(settings: Settings) -> VideoSource:
    if settings.source_type is VideoSourceType.DUMMY_VIDEO:
        return DummyVideoSource(
            path=settings.dummy_video_path,
            source_id=settings.source_id,
            session_id=settings.session_id,
            drone_id=settings.drone_id,
            loop=settings.loop_video,
            realtime=settings.realtime_playback,
        )

    if settings.source_type is VideoSourceType.DJI_LIVE:
        return create_dji_live_source(settings)

    if settings.source_type is VideoSourceType.SMARTPHONE_LIVE:
        if settings.smartphone_input_mode is SmartphoneInputMode.BROWSER_UPLOAD:
            return BrowserUploadSource(
                fps=settings.browser_upload_fps,
                queue_capacity=settings.browser_upload_queue_capacity,
            )

        return SmartphoneLiveSource(
            stream_url=settings.smartphone_stream_url,
            source_id=settings.source_id,
            session_id=settings.session_id,
            drone_id=settings.drone_id,
            reconnect=settings.smartphone_reconnect,
            reconnect_delay_seconds=settings.smartphone_reconnect_delay_seconds,
            max_reconnect_attempts=settings.smartphone_max_reconnect_attempts,
            open_timeout_ms=settings.smartphone_open_timeout_ms,
            read_timeout_ms=settings.smartphone_read_timeout_ms,
        )

    raise NotImplementedError(f"{settings.source_type.value} 입력은 다음 단계에서 구현합니다.")


def create_optional_phase3_reporter(
    settings: Settings,
) -> Phase3EventReporterLike | None:
    if not settings.phase3_enabled or not settings.phase3_report_events:
        return None

    return Phase3EventReporter(
        event_url=settings.backend_phase3_event_url,
        timeout_seconds=settings.report_timeout_seconds,
        max_retries=settings.report_max_retries,
        queue_capacity=settings.report_queue_capacity,
    )


def create_optional_phase3_observer(
    settings: Settings,
    *,
    phase3_reporter: Phase3EventReporterLike | None = None,
) -> Phase3ConsoleObserver | None:
    if not settings.phase3_enabled:
        return None

    return Phase3ConsoleObserver(reporter=phase3_reporter)


def create_optional_phase3_runtime(
    *,
    settings: Settings,
    source: VideoSource,
    phase3_observer: Phase3ConsoleObserver | None = None,
) -> Phase3Runtime | None:
    if phase3_observer is None:
        return create_phase3_runtime(
            settings=settings,
            source_fps=source.fps,
        )

    return create_phase3_runtime(
        settings=settings,
        source_fps=source.fps,
        on_depth_result=phase3_observer.on_depth_result,
    )


def create_optional_phase3_frame_analyzer(
    *,
    settings: Settings,
    source: VideoSource,
    phase3_runtime: Phase3Runtime | None,
) -> Phase3FrameAnalyzer | None:
    return create_phase3_frame_analyzer(
        settings=settings,
        runtime=phase3_runtime,
        source_fps=source.fps,
    )


def run_pipeline_with_optional_phase3(
    *,
    pipeline: InferencePipeline,
    stream_server: AnalysisStreamServer | None,
    phase3_runtime: Phase3Runtime | None,
    phase3_reporter: Phase3EventReporterLike | None = None,
    phase3_observer: Phase3ConsoleObserver | None = None,
) -> None:
    try:
        if stream_server is not None:
            stream_server.start()

        if phase3_reporter is not None:
            phase3_reporter.start()

        if phase3_runtime is not None:
            phase3_runtime.start()

        pipeline.run()
    except KeyboardInterrupt:
        print("사용자 요청으로 분석을 종료합니다.", flush=True)
    finally:
        if phase3_runtime is not None:
            phase3_runtime.close()

        if phase3_reporter is not None:
            phase3_reporter.close()

        if phase3_observer is not None:
            phase3_observer.emit_summary()

        if stream_server is not None:
            stream_server.close()


def main() -> None:
    settings = Settings.from_env()
    source = create_source(settings)
    browser_upload_source = (
        source if isinstance(source, BrowserUploadSource) else None
    )
    performance_monitor = InferencePerformanceMonitor(
        model_path=settings.model_path,
        device=settings.device,
        source_type=settings.source_type.value,
        configured_input_fps=source.fps,
        thresholds=PerformanceThresholds(
            warning_p95_inference_ms=(
                settings.performance_warning_p95_ms
            ),
            critical_p95_inference_ms=(
                settings.performance_critical_p95_ms
            ),
            warning_processing_ratio=(
                settings.performance_warning_processing_ratio
            ),
            critical_processing_ratio=(
                settings.performance_critical_processing_ratio
            ),
            warning_drop_rate_pct=(
                settings.performance_warning_drop_rate_pct
            ),
            critical_drop_rate_pct=(
                settings.performance_critical_drop_rate_pct
            ),
            warning_queue_utilization_pct=(
                settings.performance_warning_queue_utilization_pct
            ),
            critical_queue_utilization_pct=(
                settings.performance_critical_queue_utilization_pct
            ),
            stale_after_seconds=(
                settings.performance_stale_after_seconds
            ),
            min_sample_count=settings.performance_min_sample_count,
        ),
    )
    detector = YoloDetector(
        model_profile=settings.model_profile,
        model_path=settings.model_path,
        require_cuda=settings.require_cuda,
        require_local_model=settings.require_local_model,
        confidence=settings.confidence,
        iou=settings.iou,
        image_size=settings.image_size,
        device=settings.device,
    )
    reporter = (
        SpringEventReporter(
            event_url=settings.backend_event_url,
            timeout_seconds=settings.report_timeout_seconds,
            max_retries=settings.report_max_retries,
            queue_capacity=settings.report_queue_capacity,
        )
        if settings.report_events
        else None
    )
    phase3_reporter = create_optional_phase3_reporter(settings)
    frame_hub = (
        AnnotatedFrameHub(jpeg_quality=settings.stream_jpeg_quality)
        if settings.stream_enabled
        else None
    )
    stream_server = (
        AnalysisStreamServer(
            hub=frame_hub,
            host=settings.stream_host,
            port=settings.stream_port,
            allowed_origins=settings.stream_allowed_origins,
            ingest_source=browser_upload_source,
            ingest_max_payload_bytes=settings.browser_upload_max_payload_bytes,
            performance_monitor=performance_monitor,
            model_status_provider=detector.status,
            internal_security_enabled=settings.ai_internal_security_enabled,
            internal_api_key=settings.ai_internal_key,
            dji_bridge_api_key=settings.dji_bridge_key,
        )
        if frame_hub is not None
        else None
    )
    phase3_observer = create_optional_phase3_observer(
        settings,
        phase3_reporter=phase3_reporter,
    )
    phase3_runtime = create_optional_phase3_runtime(
        settings=settings,
        source=source,
        phase3_observer=phase3_observer,
    )
    phase3_analyzer = create_optional_phase3_frame_analyzer(
        settings=settings,
        source=source,
        phase3_runtime=phase3_runtime,
    )
    pipeline = InferencePipeline(
        source=source,
        detector=detector,
        phase3_analyzer=phase3_analyzer,
        phase3_observer=phase3_observer,
        save_annotated_video=settings.save_annotated_video,
        output_video_path=settings.output_video_path,
        show_preview=settings.show_preview,
        max_frames=settings.max_frames,
        reporter=reporter,
        frame_hub=frame_hub,
        snapshot_policy=settings.snapshot_policy,
        snapshot_jpeg_quality=settings.snapshot_jpeg_quality,
        event_min_consecutive_frames=(
            settings.event_min_consecutive_frames
        ),
        event_cooldown_seconds=(
            settings.event_cooldown_seconds
        ),
        performance_monitor=performance_monitor,
    )

    run_pipeline_with_optional_phase3(
        pipeline=pipeline,
        stream_server=stream_server,
        phase3_runtime=phase3_runtime,
        phase3_reporter=phase3_reporter,
        phase3_observer=phase3_observer,
    )


if __name__ == "__main__":
    main()
