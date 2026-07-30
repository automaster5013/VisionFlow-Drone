"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useOperatorAccess } from "@/components/security/operator-access-provider";
import { useMobileDroneSensors } from "@/hooks/use-mobile-drone-sensors";
import type { AiBrowserIngestStatus } from "@/types/ai-browser-ingest";
import type {
  FlightSessionManagementResponse,
  FlightSessionStartPayload,
} from "@/types/flight-session-management";
import type {
  MobileSensorSnapshot,
  MobileTelemetryPayload,
} from "@/types/mobile-telemetry";
import {
  parseMaintenanceFlightClearance,
  type MaintenanceFlightClearance,
} from "@/types/maintenance-flight-clearance";

import { MobileAiInferencePreview } from "./mobile-ai-inference-preview";

interface DroneOption {
  id: number;
  droneCode: string;
  name: string;
}

interface ManualTelemetry {
  latitude: number;
  longitude: number;
  altitude: number;
  heading: number;
  pitch: number;
  roll: number;
  groundSpeed: number;
  horizontalAccuracy: number;
  verticalAccuracy: number;
}

type FacingMode = "environment" | "user";
type SessionAction = "starting" | "completing" | "aborting";

const READY_STATE_CURRENT_DATA = 2;

const DEFAULT_MANUAL_TELEMETRY: ManualTelemetry = {
  latitude: 37.5665,
  longitude: 126.978,
  altitude: 30,
  heading: 0,
  pitch: 0,
  roll: 0,
  groundSpeed: 0,
  horizontalAccuracy: 5,
  verticalAccuracy: 8,
};

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

function isFlightSessionResponse(
  value: unknown,
): value is FlightSessionManagementResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Partial<FlightSessionManagementResponse>;

  return (
    typeof candidate.sessionId === "string" &&
    typeof candidate.droneId === "number" &&
    typeof candidate.name === "string" &&
    (candidate.status === "READY" ||
      candidate.status === "ACTIVE" ||
      candidate.status === "COMPLETED" ||
      candidate.status === "ABORTED") &&
    typeof candidate.startedAt === "string" &&
    (typeof candidate.endedAt === "string" || candidate.endedAt === null) &&
    typeof candidate.durationSeconds === "number"
  );
}

function parseFlightSessionResponse(
  payload: unknown,
): FlightSessionManagementResponse | null {
  if (isFlightSessionResponse(payload)) {
    return payload;
  }

  if (typeof payload === "object" && payload !== null && "data" in payload) {
    const data = (payload as { data?: unknown }).data;

    return isFlightSessionResponse(data) ? data : null;
  }

  return null;
}

async function readApiError(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const payload: unknown = await response.json();

    if (typeof payload === "object" && payload !== null) {
      const candidate = payload as { message?: unknown; detail?: unknown };

      if (typeof candidate.message === "string") {
        return candidate.message;
      }

      if (typeof candidate.detail === "string") {
        return candidate.detail;
      }
    }
  } catch {
    return fallback;
  }

  return fallback;
}

function formatSessionTime(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }

  const timestamp = new Date(value).getTime();

  return Number.isFinite(timestamp)
    ? new Date(timestamp).toLocaleTimeString("ko-KR")
    : value;
}

function normalizeHeading(value: number): number {
  return ((value % 360) + 360) % 360;
}

function optionalNumber(value: number | null): number | undefined {
  return value !== null && Number.isFinite(value) ? value : undefined;
}

function formatNumber(value: number | null, fractionDigits = 2): string {
  return value !== null && Number.isFinite(value)
    ? value.toFixed(fractionDigits)
    : "-";
}

function canvasToJpeg(
  canvas: HTMLCanvasElement,
  quality: number,
): Promise<Blob | null> {
  return new Promise((resolve) => {
    canvas.toBlob(resolve, "image/jpeg", quality);
  });
}

export function MobileFlightControl() {
  const { canOperate, operateDeniedReason } = useOperatorAccess();
  const {
    snapshot: sensorSnapshot,
    status: sensorStatus,
    orientationMode,
    error: sensorError,
    warning: sensorWarning,
    start: startSensors,
    stop: stopSensors,
    getSnapshot,
  } = useMobileDroneSensors();

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const sessionIdRef = useRef("");
  const activeDroneIdRef = useRef<number | null>(null);
  const transitionInFlightRef = useRef(false);
  const telemetryInFlightRef = useRef(false);
  const cameraInFlightRef = useRef(false);

  const [drones, setDrones] = useState<DroneOption[]>([]);
  const [selectedDroneId, setSelectedDroneId] = useState<number | null>(null);
  const [loadingDrones, setLoadingDrones] = useState(true);
  const [deviceId, setDeviceId] = useState("visionflow-phone-001");
  const [sessionName, setSessionName] = useState(
    "스마트폰 가상 드론 비행",
  );
  const [batteryLevel, setBatteryLevel] = useState(100);
  const [manualMode, setManualMode] = useState(true);
  const [manualTelemetry, setManualTelemetry] = useState<ManualTelemetry>(
    DEFAULT_MANUAL_TELEMETRY,
  );
  const [facingMode, setFacingMode] = useState<FacingMode>("user");
  const [framesPerSecond, setFramesPerSecond] = useState(5);
  const [maxWidth, setMaxWidth] = useState(960);
  const [jpegQuality, setJpegQuality] = useState(0.75);
  const [running, setRunning] = useState(false);
  const [session, setSession] =
    useState<FlightSessionManagementResponse | null>(null);
  const [sessionAction, setSessionAction] =
    useState<SessionAction | null>(null);
  const [telemetryCount, setTelemetryCount] = useState(0);
  const [cameraFrameCount, setCameraFrameCount] = useState(0);
  const [cameraBytes, setCameraBytes] = useState(0);
  const [lastTelemetryAt, setLastTelemetryAt] = useState<Date | null>(null);
  const [lastCameraAt, setLastCameraAt] = useState<Date | null>(null);
  const [ingestStatus, setIngestStatus] =
    useState<AiBrowserIngestStatus | null>(null);
  const [startupError, setStartupError] = useState<string | null>(null);
  const [lifecycleError, setLifecycleError] = useState<string | null>(null);
  const [telemetryError, setTelemetryError] = useState<string | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [flightClearance, setFlightClearance] =
    useState<MaintenanceFlightClearance | null>(null);
  const [clearanceReloadToken, setClearanceReloadToken] = useState(0);

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
      } catch (error) {
        if (!abortController.signal.aborted) {
          setStartupError(
            error instanceof Error
              ? error.message
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

  useEffect(() => {
    if (selectedDroneId === null) {
      return;
    }

    const abortController = new AbortController();

    fetch(`/api/maintenance/flight-clearance/${selectedDroneId}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal: abortController.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(
            await readApiError(
              response,
              `비행 허가 상태 조회 실패: ${response.status}`,
            ),
          );
        }
        return response.json() as Promise<unknown>;
      })
      .then((payload) => {
        const parsed = parseMaintenanceFlightClearance(payload);
        if (!parsed || parsed.droneId !== selectedDroneId) {
          throw new Error("비행 허가 상태 응답 형식이 올바르지 않습니다.");
        }
        if (!abortController.signal.aborted) {
          setFlightClearance(parsed);
        }
      })
      .catch((error: unknown) => {
        if (!abortController.signal.aborted) {
          setStartupError(
            error instanceof Error
              ? error.message
              : "비행 허가 상태를 확인하지 못했습니다.",
          );
        }
      });

    return () => {
      abortController.abort();
    };
  }, [clearanceReloadToken, selectedDroneId]);

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

  useEffect(() => {
    function abortActiveSessionOnPageExit() {
      const activeDroneId = activeDroneIdRef.current;
      const activeSessionId = sessionIdRef.current;

      if (
        transitionInFlightRef.current ||
        activeDroneId === null ||
        activeSessionId.length === 0 ||
        typeof navigator.sendBeacon !== "function"
      ) {
        return;
      }

      navigator.sendBeacon(
        `/api/drones/${activeDroneId}/flight-sessions/` +
          `${encodeURIComponent(activeSessionId)}/abort`,
      );
    }

    window.addEventListener("pagehide", abortActiveSessionOnPageExit);

    return () => {
      window.removeEventListener("pagehide", abortActiveSessionOnPageExit);
    };
  }, []);

  const displaySnapshot = useMemo<MobileSensorSnapshot>(() => {
    if (!manualMode) {
      return sensorSnapshot;
    }

    return {
      ...manualTelemetry,
      capturedAt: null,
    };
  }, [manualMode, manualTelemetry, sensorSnapshot]);

  const sendTelemetry = useCallback(async () => {
    if (
      telemetryInFlightRef.current ||
      selectedDroneId === null ||
      sessionIdRef.current.length === 0
    ) {
      return;
    }

    const snapshot: MobileSensorSnapshot = manualMode
      ? {
          ...manualTelemetry,
          capturedAt: null,
        }
      : getSnapshot();

    if (snapshot.latitude === null || snapshot.longitude === null) {
      setTelemetryError("GPS 좌표를 기다리고 있습니다.");
      return;
    }

    const payload: MobileTelemetryPayload = {
      latitude: snapshot.latitude,
      longitude: snapshot.longitude,
      altitude: optionalNumber(snapshot.altitude),
      batteryLevel,
      heading:
        snapshot.heading === null
          ? undefined
          : normalizeHeading(snapshot.heading),
      pitch: optionalNumber(snapshot.pitch),
      roll: optionalNumber(snapshot.roll),
      groundSpeed: optionalNumber(snapshot.groundSpeed),
      horizontalAccuracy: optionalNumber(snapshot.horizontalAccuracy),
      verticalAccuracy: optionalNumber(snapshot.verticalAccuracy),
      telemetrySource: "MOBILE_SENSOR",
      sourceDeviceId: deviceId.trim(),
      flightSessionId: sessionIdRef.current,
    };

    telemetryInFlightRef.current = true;

    try {
      const response = await fetch(
        `/api/drones/${selectedDroneId}/telemetry`,
        {
          method: "PATCH",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
          cache: "no-store",
        },
      );

      if (!response.ok) {
        throw new Error(
          `텔레메트리 전송 실패: ${response.status} ${await response.text()}`,
        );
      }

      setTelemetryError(null);
      setTelemetryCount((current) => current + 1);
      setLastTelemetryAt(new Date());
    } catch (error) {
      setTelemetryError(
        error instanceof Error
          ? error.message
          : "텔레메트리를 전송하지 못했습니다.",
      );
    } finally {
      telemetryInFlightRef.current = false;
    }
  }, [
    batteryLevel,
    deviceId,
    getSnapshot,
    manualMode,
    manualTelemetry,
    selectedDroneId,
  ]);

  const sendCameraFrame = useCallback(async () => {
    if (
      cameraInFlightRef.current ||
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
      setCameraError("카메라 프레임 캔버스를 만들 수 없습니다.");
      return;
    }

    context.drawImage(video, 0, 0, width, height);
    const jpeg = await canvasToJpeg(canvas, jpegQuality);

    if (jpeg === null) {
      setCameraError("카메라 프레임 JPEG 변환에 실패했습니다.");
      return;
    }

    const query = new URLSearchParams({
      droneId: String(selectedDroneId),
      sourceId: deviceId.trim(),
      sessionId: sessionIdRef.current,
      capturedAt: new Date().toISOString(),
    });

    cameraInFlightRef.current = true;

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

      if (!response.ok) {
        throw new Error(
          `카메라 프레임 전송 실패: ${response.status} ${await response.text()}`,
        );
      }

      setCameraError(null);
      setCameraFrameCount((current) => current + 1);
      setCameraBytes((current) => current + jpeg.size);
      setLastCameraAt(new Date());
    } catch (error) {
      setCameraError(
        error instanceof Error
          ? error.message
          : "카메라 프레임을 전송하지 못했습니다.",
      );
    } finally {
      cameraInFlightRef.current = false;
    }
  }, [deviceId, jpegQuality, maxWidth, selectedDroneId]);

  useEffect(() => {
    if (!running) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void sendTelemetry();
    }, 1_000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [running, sendTelemetry]);

  useEffect(() => {
    if (!running) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void sendCameraFrame();
    }, Math.round(1_000 / framesPerSecond));

    return () => {
      window.clearInterval(intervalId);
    };
  }, [framesPerSecond, running, sendCameraFrame]);

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
        // 전송 오류가 별도로 표시되므로 상태 폴링은 다음 주기에 재시도합니다.
      }
    }, 1_000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [running]);

  async function startFlight() {
    if (!canOperate) {
      setStartupError(operateDeniedReason);
      return;
    }

    if (selectedDroneId === null) {
      setStartupError("연결할 드론을 선택해 주세요.");
      return;
    }

    if (
      flightClearance?.droneId === selectedDroneId &&
      !flightClearance.flightAllowed
    ) {
      setStartupError(flightClearance.reason);
      return;
    }

    const normalizedDeviceId = deviceId.trim();

    if (!normalizedDeviceId) {
      setStartupError("스마트폰 식별값을 입력해 주세요.");
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setStartupError("이 브라우저는 카메라 촬영을 지원하지 않습니다.");
      return;
    }

    if (session?.status === "ACTIVE") {
      setStartupError(
        "기존 ACTIVE 세션을 완료하거나 중단한 뒤 새 비행을 시작하세요.",
      );
      return;
    }

    setSessionAction("starting");
    setStartupError(null);
    setLifecycleError(null);
    setTelemetryError(null);
    setCameraError(null);

    try {
      if (!manualMode) {
        const sensorsStarted = await startSensors();

        if (!sensorsStarted) {
          throw new Error("스마트폰 센서를 시작하지 못했습니다.");
        }
      }

      const mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: facingMode },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });
      const video = videoRef.current;

      if (video === null) {
        mediaStream.getTracks().forEach((track) => track.stop());
        throw new Error("카메라 미리보기 요소를 찾을 수 없습니다.");
      }

      mediaStreamRef.current = mediaStream;
      video.srcObject = mediaStream;
      await video.play();

      const startPayload: FlightSessionStartPayload = {
        name: sessionName.trim() || undefined,
        description: manualMode
          ? "PC 수동 텔레메트리와 브라우저 카메라 통합 비행"
          : "스마트폰 실센서와 브라우저 카메라 통합 비행",
        sourceDeviceId: normalizedDeviceId,
      };
      const response = await fetch(
        `/api/drones/${selectedDroneId}/flight-sessions`,
        {
          method: "POST",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify(startPayload),
          cache: "no-store",
        },
      );

      if (!response.ok) {
        throw new Error(
          await readApiError(
            response,
            `비행 세션 시작 실패: ${response.status}`,
          ),
        );
      }

      const nextSession = parseFlightSessionResponse(await response.json());

      if (nextSession === null || nextSession.status !== "ACTIVE") {
        throw new Error("비행 세션 시작 응답 형식이 올바르지 않습니다.");
      }

      if (nextSession.droneId !== selectedDroneId) {
        throw new Error("선택한 드론과 발급된 세션의 드론 ID가 다릅니다.");
      }

      sessionIdRef.current = nextSession.sessionId;
      activeDroneIdRef.current = nextSession.droneId;
      setSession(nextSession);
      setTelemetryCount(0);
      setCameraFrameCount(0);
      setCameraBytes(0);
      setLastTelemetryAt(null);
      setLastCameraAt(null);
      setIngestStatus(null);
      setRunning(true);
    } catch (error) {
      stopSensors();
      releaseCamera();
      setStartupError(
        error instanceof Error
          ? error.message
          : "통합 비행을 시작하지 못했습니다.",
      );
    } finally {
      setSessionAction(null);
    }
  }

  async function transitionFlight(action: "complete" | "abort") {
    if (!canOperate) {
      setLifecycleError(operateDeniedReason);
      return;
    }

    if (session === null || session.status !== "ACTIVE") {
      setLifecycleError("상태를 변경할 ACTIVE 비행 세션이 없습니다.");
      return;
    }

    const nextAction: SessionAction =
      action === "complete" ? "completing" : "aborting";

    setSessionAction(nextAction);
    transitionInFlightRef.current = true;
    setLifecycleError(null);
    setRunning(false);
    stopSensors();
    releaseCamera();

    try {
      const response = await fetch(
        `/api/drones/${session.droneId}/flight-sessions/` +
          `${encodeURIComponent(session.sessionId)}/${action}`,
        {
          method: "POST",
          headers: { Accept: "application/json" },
          cache: "no-store",
          keepalive: true,
        },
      );

      if (!response.ok) {
        throw new Error(
          await readApiError(
            response,
            `비행 세션 상태 변경 실패: ${response.status}`,
          ),
        );
      }

      const nextSession = parseFlightSessionResponse(await response.json());
      const expectedStatus =
        action === "complete" ? "COMPLETED" : "ABORTED";

      if (nextSession === null || nextSession.status !== expectedStatus) {
        throw new Error("비행 세션 상태 응답 형식이 올바르지 않습니다.");
      }

      setSession(nextSession);
      sessionIdRef.current = "";
      activeDroneIdRef.current = null;
    } catch (error) {
      setLifecycleError(
        error instanceof Error
          ? error.message
          : "비행 세션 상태를 변경하지 못했습니다.",
      );
    } finally {
      transitionInFlightRef.current = false;
      setSessionAction(null);
    }
  }

  function updateManualField(
    field: keyof ManualTelemetry,
    value: number,
  ) {
    setManualTelemetry((current) => ({
      ...current,
      [field]: value,
    }));
  }

  const hasActiveSession = session?.status === "ACTIVE";
  const sessionStatusLabel =
    sessionAction === "starting"
      ? "STARTING"
      : sessionAction === "completing"
        ? "COMPLETING"
        : sessionAction === "aborting"
          ? "ABORTING"
          : session?.status ?? "STOPPED";
  const sessionStatusClass = running
    ? "bg-emerald-600 text-white"
    : sessionAction !== null
      ? "bg-amber-500 text-white"
      : session?.status === "COMPLETED"
        ? "bg-blue-600 text-white"
        : session?.status === "ABORTED"
          ? "bg-red-600 text-white"
          : session?.status === "ACTIVE"
            ? "bg-amber-100 text-amber-900"
            : "bg-slate-200 text-slate-700";
  const replayHref =
    session !== null &&
    selectedDroneId !== null &&
    (session.status === "COMPLETED" || session.status === "ABORTED")
      ? `/drones?${new URLSearchParams({
          droneId: String(selectedDroneId),
          sessionId: session.sessionId,
        }).toString()}#flight-session-replay`
      : null;
  const currentFlightClearance =
    flightClearance?.droneId === selectedDroneId
      ? flightClearance
      : null;
  const flightGateBlocked =
    currentFlightClearance !== null &&
    !currentFlightClearance.flightAllowed;

  return (
    <main className="min-h-screen bg-slate-100 px-4 py-6 text-slate-900">
      <div className="mx-auto max-w-7xl space-y-4">
        <header className="rounded-2xl bg-slate-950 p-5 text-white shadow-lg">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-xs font-bold tracking-[0.2em] text-cyan-400">
                VISIONFLOW UNIFIED FLIGHT
              </div>
              <h1 className="mt-2 text-2xl font-bold">
                가상 드론 통합 비행 세션
              </h1>
              <p className="mt-2 text-sm text-slate-300">
                위치·방향 텔레메트리와 AI 카메라 영상을 동일한 세션으로 전송합니다.
              </p>
            </div>

            <div className="flex gap-2">
              <Link
                href="/mobile-control"
                className="rounded-lg border border-slate-600 px-3 py-2 text-sm font-semibold"
              >
                센서 화면
              </Link>
              <Link
                href="/drones"
                className="rounded-lg border border-slate-600 px-3 py-2 text-sm font-semibold"
              >
                관제 화면
              </Link>
            </div>
          </div>
        </header>

        <section className="rounded-2xl border border-cyan-200 bg-cyan-50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-xs font-semibold text-cyan-700">
                서버 관리 비행 세션
              </div>
              <div className="mt-1 font-bold text-cyan-950">
                {session?.name ?? "비행 시작 전"}
              </div>
              <div className="mt-1 break-all font-mono text-sm font-bold text-cyan-950">
                {session?.sessionId ??
                  "비행을 시작하면 서버가 UUID를 발급합니다."}
              </div>
              {session && (
                <div className="mt-1 text-xs text-cyan-800">
                  시작 {formatSessionTime(session.startedAt)} · 종료{" "}
                  {formatSessionTime(session.endedAt)}
                </div>
              )}
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <span
                className={`rounded-full px-3 py-1 text-sm font-bold ${sessionStatusClass}`}
              >
                {running ? "● FLIGHT ACTIVE" : sessionStatusLabel}
              </span>

              {replayHref && (
                <Link
                  href={replayHref}
                  className="rounded-lg bg-cyan-950 px-3 py-2 text-sm font-bold text-white transition hover:bg-cyan-800"
                >
                  완료 세션 관제 리플레이
                </Link>
              )}
            </div>
          </div>
        </section>

        <section className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-5 md:grid-cols-2">
          <label className="text-sm font-semibold text-slate-700">
            연결할 드론
            <select
              value={selectedDroneId ?? ""}
              onChange={(event) =>
                setSelectedDroneId(Number(event.target.value))
              }
              disabled={
                loadingDrones ||
                running ||
                hasActiveSession ||
                sessionAction !== null
              }
              className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-3"
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

          <label className="text-sm font-semibold text-slate-700">
            스마트폰·영상 소스 식별값
            <input
              type="text"
              value={deviceId}
              maxLength={100}
              disabled={running || hasActiveSession || sessionAction !== null}
              onChange={(event) => setDeviceId(event.target.value)}
              className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-3"
            />
          </label>

          <label className="text-sm font-semibold text-slate-700 md:col-span-2">
            비행 세션명
            <input
              type="text"
              value={sessionName}
              maxLength={120}
              disabled={running || hasActiveSession || sessionAction !== null}
              placeholder="예: 오후 안전 점검 비행"
              onChange={(event) => setSessionName(event.target.value)}
              className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-3"
            />
          </label>

          <label className="text-sm font-semibold text-slate-700">
            카메라
            <select
              value={facingMode}
              disabled={running || hasActiveSession || sessionAction !== null}
              onChange={(event) =>
                setFacingMode(event.target.value as FacingMode)
              }
              className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-3"
            >
              <option value="user">전면 카메라 · PC 권장</option>
              <option value="environment">후면 카메라 · 스마트폰 권장</option>
            </select>
          </label>

          <label className="text-sm font-semibold text-slate-700">
            카메라 전송 속도
            <select
              value={framesPerSecond}
              disabled={running || hasActiveSession || sessionAction !== null}
              onChange={(event) =>
                setFramesPerSecond(Number(event.target.value))
              }
              className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-3"
            >
              <option value={2}>2 FPS</option>
              <option value={5}>5 FPS · 권장</option>
              <option value={10}>10 FPS</option>
            </select>
          </label>

          <label className="text-sm font-semibold text-slate-700">
            최대 영상 폭
            <select
              value={maxWidth}
              disabled={running || hasActiveSession || sessionAction !== null}
              onChange={(event) => setMaxWidth(Number(event.target.value))}
              className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-3"
            >
              <option value={640}>640px</option>
              <option value={960}>960px · 권장</option>
              <option value={1280}>1280px</option>
            </select>
          </label>

          <label className="text-sm font-semibold text-slate-700">
            JPEG 품질 {Math.round(jpegQuality * 100)}%
            <input
              type="range"
              min={0.5}
              max={0.9}
              step={0.05}
              value={jpegQuality}
              disabled={running || hasActiveSession || sessionAction !== null}
              onChange={(event) => setJpegQuality(Number(event.target.value))}
              className="mt-4 w-full"
            />
          </label>

          <label className="text-sm font-semibold text-slate-700 md:col-span-2">
            가상 배터리 {batteryLevel}%
            <input
              type="range"
              min={0}
              max={100}
              value={batteryLevel}
              onChange={(event) => setBatteryLevel(Number(event.target.value))}
              className="mt-2 w-full"
            />
          </label>

          <label className="flex items-center gap-3 rounded-xl bg-amber-50 p-3 text-sm font-semibold text-amber-900 md:col-span-2">
            <input
              type="checkbox"
              checked={manualMode}
              disabled={running || hasActiveSession || sessionAction !== null}
              onChange={(event) => setManualMode(event.target.checked)}
              className="h-5 w-5"
            />
            PC 검증용 수동 텔레메트리 모드
          </label>
        </section>

        {selectedDroneId !== null && (
          <section
            className={[
              "rounded-2xl border p-4",
              currentFlightClearance === null
                ? "border-slate-200 bg-white"
                : flightGateBlocked
                  ? "border-red-300 bg-red-50"
                  : currentFlightClearance.attentionRequired
                    ? "border-amber-300 bg-amber-50"
                    : "border-emerald-300 bg-emerald-50",
            ].join(" ")}
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-xs font-bold uppercase tracking-wider text-slate-600">
                  Maintenance Flight Clearance
                </div>
                <div className="mt-1 font-bold text-slate-950">
                  {currentFlightClearance === null
                    ? "기체 비행 허가 상태 확인 중"
                    : `게이트 ${currentFlightClearance.mode} · ${
                        currentFlightClearance.flightAllowed
                          ? "시작 가능"
                          : "시작 차단"
                      }`}
                </div>
                {currentFlightClearance && (
                  <p className="mt-1 text-sm text-slate-700">
                    {currentFlightClearance.reason}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {currentFlightClearance?.workOrderId && (
                  <Link
                    href="/maintenance"
                    className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-bold text-slate-700"
                  >
                    작업 #{currentFlightClearance.workOrderId} 열기
                  </Link>
                )}
                <button
                  type="button"
                  onClick={() =>
                    setClearanceReloadToken((current) => current + 1)
                  }
                  className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-bold text-white"
                >
                  허가 상태 새로고침
                </button>
              </div>
            </div>
          </section>
        )}

        {manualMode && (
          <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
            <h2 className="font-bold text-amber-950">수동 센서 값</h2>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
              {(
                [
                  ["latitude", "위도"],
                  ["longitude", "경도"],
                  ["altitude", "고도(m)"],
                  ["heading", "방위각(°)"],
                  ["pitch", "피치(°)"],
                  ["roll", "롤(°)"],
                  ["groundSpeed", "속도(m/s)"],
                  ["horizontalAccuracy", "수평 정확도(m)"],
                  ["verticalAccuracy", "수직 정확도(m)"],
                ] as const
              ).map(([field, label]) => (
                <label key={field} className="text-xs font-semibold text-slate-700">
                  {label}
                  <input
                    type="number"
                    step="any"
                    value={manualTelemetry[field]}
                    onChange={(event) =>
                      updateManualField(field, Number(event.target.value))
                    }
                    className="mt-1 w-full rounded-lg border border-amber-300 bg-white px-2 py-2"
                  />
                </label>
              ))}
            </div>
          </section>
        )}

        <section className="grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(300px,0.6fr)]">
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-950">
            <div className="relative flex aspect-video items-center justify-center">
              <video
                ref={videoRef}
                muted
                playsInline
                className="h-full w-full object-contain"
              />
              {!running && (
                <div className="absolute inset-0 flex items-center justify-center bg-slate-950/90 text-center text-slate-300">
                  통합 비행 시작 후 카메라가 표시됩니다.
                </div>
              )}
            </div>
            <canvas ref={canvasRef} className="hidden" />
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            <h2 className="font-bold">센서 상태</h2>
            <div className="mt-1 text-sm text-slate-500">
              {manualMode
                ? "수동 텔레메트리"
                : `${sensorStatus} · 방향 ${orientationMode}`}
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3">
              <StatusValue
                label="위도"
                value={formatNumber(displaySnapshot.latitude, 7)}
              />
              <StatusValue
                label="경도"
                value={formatNumber(displaySnapshot.longitude, 7)}
              />
              <StatusValue
                label="고도"
                value={`${formatNumber(displaySnapshot.altitude)}m`}
              />
              <StatusValue
                label="방위각"
                value={`${formatNumber(displaySnapshot.heading, 1)}°`}
              />
              <StatusValue
                label="피치"
                value={`${formatNumber(displaySnapshot.pitch, 1)}°`}
              />
              <StatusValue
                label="롤"
                value={`${formatNumber(displaySnapshot.roll, 1)}°`}
              />
            </div>
          </div>
        </section>

        <MobileAiInferencePreview expectedDroneId={selectedDroneId} />

        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatusValue label="텔레메트리" value={`${telemetryCount}회`} />
            <StatusValue label="카메라" value={`${cameraFrameCount} 프레임`} />
            <StatusValue
              label="영상 전송량"
              value={`${(cameraBytes / 1_000_000).toFixed(2)} MB`}
            />
            <StatusValue
              label="AI 큐 드롭"
              value={`${ingestStatus?.droppedFrames ?? 0} 프레임`}
            />
          </div>

          <div className="mt-3 text-center text-xs text-slate-500">
            시작 {formatSessionTime(session?.startedAt)} · 텔레메트리 성공{" "}
            {lastTelemetryAt?.toLocaleTimeString("ko-KR") ?? "-"} · 카메라 성공{" "}
            {lastCameraAt?.toLocaleTimeString("ko-KR") ?? "-"}
          </div>

          {(startupError ||
            lifecycleError ||
            sensorError ||
            telemetryError ||
            cameraError) && (
            <div className="mt-4 rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800">
              {startupError ??
                lifecycleError ??
                sensorError ??
                telemetryError ??
                cameraError}
            </div>
          )}

          {sensorWarning && !manualMode && (
            <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
              {sensorWarning}
            </div>
          )}

          <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
            현재 PC에서는 수동 텔레메트리와 웹캠으로 검증합니다. 스마트폰 실제 센서·카메라는 신뢰된 HTTPS 인증서 적용 후 같은 화면에서 확인합니다.
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <button
              type="button"
              onClick={() => void startFlight()}
              disabled={
                running ||
                hasActiveSession ||
                selectedDroneId === null ||
                !canOperate ||
                flightGateBlocked ||
                sessionAction !== null
              }
              title={
                flightGateBlocked
                  ? currentFlightClearance?.reason
                  : canOperate
                    ? undefined
                    : operateDeniedReason ?? undefined
              }
              className="rounded-xl bg-cyan-600 px-4 py-3 font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              {sessionAction === "starting"
                ? "세션 생성 중"
                : "통합 비행 시작"}
            </button>
            <button
              type="button"
              onClick={() => void transitionFlight("complete")}
              disabled={!hasActiveSession || sessionAction !== null || !canOperate}
              title={canOperate ? undefined : operateDeniedReason ?? undefined}
              className="rounded-xl bg-slate-900 px-4 py-3 font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              {sessionAction === "completing"
                ? "완료 처리 중"
                : running
                  ? "비행 종료·완료"
                  : "완료 재시도"}
            </button>
            <button
              type="button"
              onClick={() => void transitionFlight("abort")}
              disabled={!hasActiveSession || sessionAction !== null || !canOperate}
              title={canOperate ? undefined : operateDeniedReason ?? undefined}
              className="rounded-xl bg-red-700 px-4 py-3 font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              {sessionAction === "aborting" ? "중단 처리 중" : "비행 중단"}
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}

function StatusValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-3 text-center">
      <div className="text-xs font-semibold text-slate-500">{label}</div>
      <div className="mt-1 font-bold text-slate-900">{value}</div>
    </div>
  );
}
