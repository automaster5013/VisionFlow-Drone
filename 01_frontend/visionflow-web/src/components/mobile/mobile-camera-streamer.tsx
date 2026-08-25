"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type {
  AiBrowserFrameUploadResponse,
  AiBrowserIngestStatus,
} from "@/types/ai-browser-ingest";

import { MobileAiInferencePreview } from "./mobile-ai-inference-preview";

interface DroneOption {
  id: number;
  droneCode: string;
  name: string;
}

interface CameraDeviceOption {
  deviceId: string;
  label: string;
}

type FacingMode = "environment" | "user";

const READY_STATE_CURRENT_DATA = 2;
const VIRTUAL_CAMERA_PATTERN =
  /(virtual|obs|broadcast|droidcam|iriun|manycam|snap camera|powertoys)/i;

function isDroneOption(value: unknown): value is DroneOption {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Partial<DroneOption>;

  return (
    typeof candidate.id === "number" &&
    Number.isFinite(candidate.id) &&
    typeof candidate.droneCode === "string" &&
    typeof candidate.name === "string"
  );
}

function parseDroneOptions(payload: unknown): DroneOption[] {
  const candidates = Array.isArray(payload)
    ? payload
    : typeof payload === "object" &&
        payload !== null &&
        "data" in payload &&
        Array.isArray((payload as { data?: unknown }).data)
      ? (payload as { data: unknown[] }).data
      : [];

  return candidates.filter(isDroneOption);
}

function isIngestStatus(value: unknown): value is AiBrowserIngestStatus {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Partial<AiBrowserIngestStatus>;

  return (
    typeof candidate.enabled === "boolean" &&
    typeof candidate.running === "boolean" &&
    typeof candidate.queueDepth === "number" &&
    typeof candidate.acceptedFrames === "number" &&
    typeof candidate.droppedFrames === "number"
  );
}

function isUploadResponse(
  value: unknown,
): value is AiBrowserFrameUploadResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Partial<AiBrowserFrameUploadResponse>;

  return (
    candidate.accepted === true &&
    typeof candidate.queueDepth === "number" &&
    typeof candidate.acceptedFrames === "number" &&
    typeof candidate.droppedFrames === "number"
  );
}

function createSessionId(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }

  return `camera-${Date.now().toString(36)}`;
}

function canvasToJpeg(
  canvas: HTMLCanvasElement,
  quality: number,
): Promise<Blob | null> {
  return new Promise((resolve) => {
    canvas.toBlob(resolve, "image/jpeg", quality);
  });
}

function cameraErrorMessage(error: unknown): string {
  if (!(error instanceof DOMException)) {
    return error instanceof Error
      ? error.message
      : "카메라를 시작하지 못했습니다.";
  }

  switch (error.name) {
    case "NotAllowedError":
      return "브라우저 또는 Windows에서 카메라 사용 권한이 거부되었습니다.";
    case "NotFoundError":
      return "사용 가능한 카메라 장치를 찾지 못했습니다.";
    case "NotReadableError":
      return "선택한 카메라를 열 수 없습니다. 다른 카메라 앱을 종료한 뒤 다시 시도하세요.";
    case "OverconstrainedError":
      return "선택한 카메라가 연결되어 있지 않거나 요청한 설정을 지원하지 않습니다.";
    default:
      return error.message || "카메라를 시작하지 못했습니다.";
  }
}

export function MobileCameraStreamer() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const sessionIdRef = useRef("");
  const uploadInFlightRef = useRef(false);

  const [drones, setDrones] = useState<DroneOption[]>([]);
  const [selectedDroneId, setSelectedDroneId] = useState<number | null>(null);
  const [loadingDrones, setLoadingDrones] = useState(true);
  const [sourceId, setSourceId] = useState("browser-camera-001");
  const [cameraDevices, setCameraDevices] = useState<CameraDeviceOption[]>([]);
  const [selectedCameraId, setSelectedCameraId] = useState("");
  const [activeCameraLabel, setActiveCameraLabel] = useState<string | null>(
    null,
  );
  const [activeCameraResolution, setActiveCameraResolution] = useState<
    string | null
  >(null);
  const [cameraWarning, setCameraWarning] = useState<string | null>(null);
  const [facingMode, setFacingMode] = useState<FacingMode>("user");
  const [framesPerSecond, setFramesPerSecond] = useState(5);
  const [maxWidth, setMaxWidth] = useState(960);
  const [jpegQuality, setJpegQuality] = useState(0.75);
  const [running, setRunning] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [uploadedFrames, setUploadedFrames] = useState(0);
  const [uploadedBytes, setUploadedBytes] = useState(0);
  const [lastUploadedAt, setLastUploadedAt] = useState<Date | null>(null);
  const [ingestStatus, setIngestStatus] =
    useState<AiBrowserIngestStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const abortController = new AbortController();

    async function loadDrones() {
      try {
        const response = await fetch("/api/drones", {
          method: "GET",
          headers: { Accept: "application/json" },
          cache: "no-store",
          signal: abortController.signal,
        });

        if (!response.ok) {
          throw new Error(`드론 목록 조회 실패: ${response.status}`);
        }

        const options = parseDroneOptions(await response.json());

        if (abortController.signal.aborted) {
          return;
        }

        setDrones(options);
        setSelectedDroneId(options[0]?.id ?? null);
      } catch (loadError) {
        if (!abortController.signal.aborted) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "드론 목록을 불러오지 못했습니다.",
          );
        }
      } finally {
        if (!abortController.signal.aborted) {
          setLoadingDrones(false);
        }
      }
    }

    void loadDrones();

    return () => {
      abortController.abort();
    };
  }, []);

  const refreshCameraDevices = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) {
      return [] as CameraDeviceOption[];
    }

    const devices = (await navigator.mediaDevices.enumerateDevices())
      .filter((device) => device.kind === "videoinput")
      .map((device, index) => ({
        deviceId: device.deviceId,
        label: device.label.trim() || `카메라 ${index + 1}`,
      }));

    setCameraDevices(devices);
    return devices;
  }, []);

  useEffect(() => {
    const mediaDevices = navigator.mediaDevices;

    if (!mediaDevices?.enumerateDevices) {
      return;
    }

    const handleDeviceChange = () => {
      void refreshCameraDevices();
    };

    mediaDevices.addEventListener("devicechange", handleDeviceChange);

    return () => {
      mediaDevices.removeEventListener("devicechange", handleDeviceChange);
    };
  }, [refreshCameraDevices]);

  const releaseCamera = useCallback(() => {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;

    if (videoRef.current !== null) {
      videoRef.current.srcObject = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      releaseCamera();
    };
  }, [releaseCamera]);

  const sendFrame = useCallback(async () => {
    if (
      uploadInFlightRef.current ||
      selectedDroneId === null ||
      sessionIdRef.current.length === 0
    ) {
      return;
    }

    const video = videoRef.current;
    const canvas = canvasRef.current;

    if (
      video === null ||
      canvas === null ||
      video.readyState < READY_STATE_CURRENT_DATA ||
      video.videoWidth <= 0 ||
      video.videoHeight <= 0
    ) {
      return;
    }

    const scale = Math.min(1, maxWidth / video.videoWidth);
    const width = Math.max(1, Math.round(video.videoWidth * scale));
    const height = Math.max(1, Math.round(video.videoHeight * scale));

    canvas.width = width;
    canvas.height = height;

    const context = canvas.getContext("2d");

    if (context === null) {
      setError("카메라 프레임 캔버스를 만들 수 없습니다.");
      return;
    }

    context.drawImage(video, 0, 0, width, height);
    const jpeg = await canvasToJpeg(canvas, jpegQuality);

    if (jpeg === null) {
      setError("카메라 프레임 JPEG 변환에 실패했습니다.");
      return;
    }

    const query = new URLSearchParams({
      droneId: String(selectedDroneId),
      sourceId: sourceId.trim() || "browser-camera",
      sessionId: sessionIdRef.current,
      capturedAt: new Date().toISOString(),
    });

    uploadInFlightRef.current = true;

    try {
      const response = await fetch(`/api/ai/ingest/frame?${query.toString()}`, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "image/jpeg",
        },
        body: jpeg,
        cache: "no-store",
      });

      const payload: unknown = await response.json();

      if (!response.ok) {
        const message =
          typeof payload === "object" &&
          payload !== null &&
          "message" in payload &&
          typeof (payload as { message?: unknown }).message === "string"
            ? (payload as { message: string }).message
            : `영상 프레임 전송 실패: ${response.status}`;

        throw new Error(message);
      }

      if (!isUploadResponse(payload)) {
        throw new Error("영상 입력 응답 형식이 올바르지 않습니다.");
      }

      setError(null);
      setUploadedFrames((current) => current + 1);
      setUploadedBytes((current) => current + jpeg.size);
      setLastUploadedAt(new Date());
    } catch (uploadError) {
      setError(
        uploadError instanceof Error
          ? uploadError.message
          : "영상 프레임을 전송하지 못했습니다.",
      );
    } finally {
      uploadInFlightRef.current = false;
    }
  }, [jpegQuality, maxWidth, selectedDroneId, sourceId]);

  useEffect(() => {
    if (!running) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void sendFrame();
    }, Math.round(1_000 / framesPerSecond));

    return () => {
      window.clearInterval(intervalId);
    };
  }, [framesPerSecond, running, sendFrame]);

  useEffect(() => {
    if (!running) {
      return;
    }

    const intervalId = window.setInterval(async () => {
      try {
        const response = await fetch("/api/ai/ingest/status", {
          method: "GET",
          headers: { Accept: "application/json" },
          cache: "no-store",
        });

        if (!response.ok) {
          return;
        }

        const payload: unknown = await response.json();

        if (isIngestStatus(payload)) {
          setIngestStatus(payload);
        }
      } catch {
        // 프레임 POST 오류를 우선 표시하므로 상태 폴링 실패는 조용히 재시도합니다.
      }
    }, 1_000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [running]);

  async function startCamera() {
    if (selectedDroneId === null) {
      setError("연결할 드론을 선택해 주세요.");
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setError("이 브라우저는 카메라 촬영을 지원하지 않습니다.");
      return;
    }

    setError(null);
    setCameraWarning(null);

    try {
      let mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          ...(selectedCameraId
            ? { deviceId: { exact: selectedCameraId } }
            : { facingMode: { ideal: facingMode } }),
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });
      let videoTrack = mediaStream.getVideoTracks()[0];
      let devices = await refreshCameraDevices();
      let activeDeviceId = videoTrack?.getSettings().deviceId ?? "";
      let activeLabel =
        devices.find((device) => device.deviceId === activeDeviceId)?.label ??
        videoTrack?.label ??
        "알 수 없는 카메라";

      if (!selectedCameraId && VIRTUAL_CAMERA_PATTERN.test(activeLabel)) {
        const physicalCamera = devices.find(
          (device) => !VIRTUAL_CAMERA_PATTERN.test(device.label),
        );

        if (
          physicalCamera !== undefined &&
          physicalCamera.deviceId !== activeDeviceId
        ) {
          mediaStream.getTracks().forEach((track) => track.stop());
          mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: false,
            video: {
              deviceId: { exact: physicalCamera.deviceId },
              width: { ideal: 1280 },
              height: { ideal: 720 },
            },
          });
          videoTrack = mediaStream.getVideoTracks()[0];
          devices = await refreshCameraDevices();
          activeDeviceId = videoTrack?.getSettings().deviceId ?? "";
          activeLabel =
            devices.find((device) => device.deviceId === activeDeviceId)
              ?.label ??
            videoTrack?.label ??
            physicalCamera.label;
        }
      }

      const video = videoRef.current;

      if (video === null) {
        mediaStream.getTracks().forEach((track) => track.stop());
        throw new Error("카메라 미리보기 요소를 찾을 수 없습니다.");
      }

      mediaStreamRef.current = mediaStream;
      video.srcObject = mediaStream;
      await video.play();

      const settings = videoTrack?.getSettings();

      setSelectedCameraId(activeDeviceId);
      setActiveCameraLabel(activeLabel);
      setActiveCameraResolution(
        settings?.width && settings.height
          ? `${settings.width} × ${settings.height}`
          : null,
      );
      setCameraWarning(
        VIRTUAL_CAMERA_PATTERN.test(activeLabel)
          ? `현재 "${activeLabel}" 가상 카메라가 선택되었습니다. 빨간 X가 계속 보이면 전송을 중지하고 내장 웹캠을 선택하세요.`
          : null,
      );

      videoTrack?.addEventListener(
        "ended",
        () => {
          setRunning(false);
          setActiveCameraLabel(null);
          setActiveCameraResolution(null);
          setError("카메라 장치 연결이 종료되었습니다.");
          releaseCamera();
        },
        { once: true },
      );

      const nextSessionId = createSessionId();
      sessionIdRef.current = nextSessionId;
      setSessionId(nextSessionId);
      setUploadedFrames(0);
      setUploadedBytes(0);
      setLastUploadedAt(null);
      setIngestStatus(null);
      setRunning(true);
    } catch (cameraError) {
      releaseCamera();
      setActiveCameraLabel(null);
      setActiveCameraResolution(null);
      setError(cameraErrorMessage(cameraError));
    }
  }

  function stopCamera() {
    setRunning(false);
    setActiveCameraLabel(null);
    setActiveCameraResolution(null);
    releaseCamera();
  }

  const uploadedMegabytes = useMemo(
    () => (uploadedBytes / 1_000_000).toFixed(2),
    [uploadedBytes],
  );

  return (
    <div
      data-mobile-camera-command
      className="vf-camera-command min-h-full text-slate-900"
    >
      <div className="mx-auto max-w-[1500px] space-y-5">
        <header className="vf-camera-command__hero rounded-2xl p-5 shadow-lg sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="vf-command-eyebrow">
                Vision Input Command
              </div>
              <h1 className="mt-2 text-2xl font-black sm:text-3xl">
                AI 카메라 입력 관제
              </h1>
              <p className="mt-2 max-w-2xl text-sm text-slate-500">
                브라우저 카메라 프레임을 JPEG로 변환해 YOLO AI 서버로
                전송하고, 원본과 추론 영상을 동시에 확인합니다.
              </p>
            </div>

            <div className="flex flex-wrap items-center justify-end gap-2">
              <span
                className={`vf-camera-state ${
                  running
                    ? "vf-camera-state--live"
                    : "vf-camera-state--idle"
                }`}
              >
                <span aria-hidden="true">●</span>
                {running ? "FRAME UPLINK" : "INPUT STANDBY"}
              </span>
              <Link
                href="/mobile-control"
                className="vf-camera-command__link rounded-lg border px-3 py-2 text-sm font-semibold"
              >
                텔레메트리
              </Link>
              <Link
                href="/drones"
                className="vf-camera-command__link rounded-lg border px-3 py-2 text-sm font-semibold"
              >
                관제 화면
              </Link>
            </div>
          </div>
        </header>

        <section className="vf-camera-command__config grid gap-4 rounded-2xl border border-slate-200 bg-white p-5 sm:grid-cols-2">
          <div className="flex flex-wrap items-end justify-between gap-3 border-b border-slate-200 pb-4 sm:col-span-2">
            <div>
              <div className="vf-command-eyebrow">Capture Configuration</div>
              <h2 className="mt-1 text-lg font-black text-slate-900">
                영상 입력 설정
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                전송 중에는 입력 계약을 고정해 프레임 일관성을 유지합니다.
              </p>
            </div>
            <span className="text-xs font-bold text-slate-500">
              JPEG · POST /api/ai/ingest/frame
            </span>
          </div>

          <label className="vf-camera-field text-sm font-semibold text-slate-700">
            연결할 드론
            <select
              value={selectedDroneId ?? ""}
              onChange={(event) =>
                setSelectedDroneId(Number(event.target.value))
              }
              disabled={loadingDrones || running}
              className="vf-camera-input mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-3"
            >
              <option value="" disabled>
                {loadingDrones ? "드론 조회 중" : "드론 선택"}
              </option>
              {drones.map((drone) => (
                <option key={drone.id} value={drone.id}>
                  {drone.name} · {drone.droneCode}
                </option>
              ))}
            </select>
          </label>

          <label className="vf-camera-field text-sm font-semibold text-slate-700">
            영상 소스 ID
            <input
              type="text"
              value={sourceId}
              maxLength={100}
              disabled={running}
              onChange={(event) => setSourceId(event.target.value)}
              className="vf-camera-input mt-2 w-full rounded-lg border border-slate-300 px-3 py-3"
            />
          </label>

          <label className="vf-camera-field text-sm font-semibold text-slate-700">
            카메라 장치
            <select
              value={selectedCameraId}
              disabled={running}
              onChange={(event) => setSelectedCameraId(event.target.value)}
              className="vf-camera-input mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-3"
            >
              <option value="">브라우저 기본 카메라</option>
              {cameraDevices.map((device) => (
                <option key={device.deviceId} value={device.deviceId}>
                  {device.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={running}
              onClick={() => void refreshCameraDevices()}
              className="vf-camera-command__inline-action mt-2 text-xs font-bold disabled:opacity-40"
            >
              카메라 목록 다시 검색
            </button>
          </label>

          <label className="vf-camera-field text-sm font-semibold text-slate-700">
            기본 카메라 방향
            <select
              value={facingMode}
              disabled={running || selectedCameraId.length > 0}
              onChange={(event) =>
                setFacingMode(event.target.value as FacingMode)
              }
              className="vf-camera-input mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-3"
            >
              <option value="user">전면 카메라 · 노트북 권장</option>
              <option value="environment">후면 카메라 · 스마트폰 권장</option>
            </select>
          </label>

          <label className="vf-camera-field text-sm font-semibold text-slate-700">
            전송 속도
            <select
              value={framesPerSecond}
              disabled={running}
              onChange={(event) =>
                setFramesPerSecond(Number(event.target.value))
              }
              className="vf-camera-input mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-3"
            >
              <option value={2}>2 FPS · 저부하</option>
              <option value={5}>5 FPS · 권장</option>
              <option value={10}>10 FPS · 고속</option>
            </select>
          </label>

          <label className="vf-camera-field text-sm font-semibold text-slate-700">
            최대 영상 폭
            <select
              value={maxWidth}
              disabled={running}
              onChange={(event) => setMaxWidth(Number(event.target.value))}
              className="vf-camera-input mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-3"
            >
              <option value={640}>640px</option>
              <option value={960}>960px · 권장</option>
              <option value={1280}>1280px</option>
            </select>
          </label>

          <label className="vf-camera-field text-sm font-semibold text-slate-700">
            JPEG 품질 {Math.round(jpegQuality * 100)}%
            <input
              type="range"
              min={0.5}
              max={0.9}
              step={0.05}
              value={jpegQuality}
              disabled={running}
              onChange={(event) => setJpegQuality(Number(event.target.value))}
              className="vf-camera-range mt-4 w-full"
            />
          </label>
        </section>

        <div className="vf-camera-command__preview-grid grid gap-4 xl:grid-cols-2">
          <section className="vf-camera-command__preview overflow-hidden rounded-2xl border border-slate-200 bg-white">
            <header className="border-b border-slate-200 p-4">
              <h2 className="font-bold text-slate-900">원본 카메라 영상</h2>
              <p className="mt-1 text-xs text-slate-500">
                브라우저가 AI 서버로 전송하는 원본 프레임입니다.
              </p>
            </header>
            <div className="relative flex aspect-video items-center justify-center bg-slate-950">
              <video
                ref={videoRef}
                muted
                playsInline
                className="h-full w-full object-contain"
              />
              {!running && (
                <div className="absolute inset-0 flex items-center justify-center bg-slate-950/90 text-center text-slate-300">
                  카메라 시작을 누르면 미리보기가 표시됩니다.
                </div>
              )}
            </div>
            <canvas ref={canvasRef} className="hidden" />
          </section>

          <MobileAiInferencePreview expectedDroneId={selectedDroneId} />
        </div>

        <section className="vf-camera-command__status rounded-2xl border border-slate-200 bg-white p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="vf-command-eyebrow">Transmission Telemetry</div>
              <h2 className="mt-1 text-lg font-black text-slate-900">
                프레임 전송 상태
              </h2>
            </div>
            <span className="text-xs font-bold text-slate-500">
              세션 {sessionId || "대기"}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatusValue label="화면 전송" value={`${uploadedFrames} 프레임`} />
            <StatusValue label="전송량" value={`${uploadedMegabytes} MB`} />
            <StatusValue
              label="AI 수신"
              value={`${ingestStatus?.acceptedFrames ?? 0} 프레임`}
            />
            <StatusValue
              label="큐 드롭"
              value={`${ingestStatus?.droppedFrames ?? 0} 프레임`}
            />
          </div>

          <div className="mt-3 text-center text-xs text-slate-500">
            마지막 성공 {lastUploadedAt?.toLocaleTimeString("ko-KR") ?? "-"}
            {ingestStatus !== null && ` · AI 큐 ${ingestStatus.queueDepth}개`}
          </div>

          {error && (
            <div className="vf-camera-command__notice vf-camera-command__notice--danger mt-4 rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800">
              {error}
            </div>
          )}

          {activeCameraLabel && (
            <div className="vf-camera-command__notice vf-camera-command__notice--info mt-4 rounded-xl border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
              현재 카메라: <strong>{activeCameraLabel}</strong>
              {activeCameraResolution && ` · ${activeCameraResolution}`}
            </div>
          )}

          {cameraWarning && (
            <div className="vf-camera-command__notice vf-camera-command__notice--warning mt-4 rounded-xl border border-amber-400 bg-amber-50 p-3 text-sm font-semibold text-amber-900">
              {cameraWarning}
            </div>
          )}

          <div className="vf-camera-command__notice vf-camera-command__notice--warning mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
            스마트폰 카메라는 신뢰된 HTTPS가 필요합니다. 현재는 PC의 localhost에서 먼저 검증하세요.
          </div>

          <div className="vf-camera-command__actions mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => void startCamera()}
              disabled={running || selectedDroneId === null}
              className="vf-camera-command__start rounded-xl px-4 py-3 font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              카메라 전송 시작
            </button>
            <button
              type="button"
              onClick={stopCamera}
              disabled={!running}
              className="vf-camera-command__stop rounded-xl px-4 py-3 font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              전송 중지
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}

function StatusValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="vf-camera-command__metric rounded-xl bg-slate-50 p-3 text-center">
      <div className="text-xs font-semibold text-slate-500">{label}</div>
      <div className="mt-1 font-bold text-slate-900">{value}</div>
    </div>
  );
}
