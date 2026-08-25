"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

type DemoMode = "IDLE" | "PHONE" | "DUMMY";

interface IngestResponse {
  accepted?: boolean;
  droppedPreviousFrame?: boolean;
  queueDepth?: number;
  acceptedFrames?: number;
  droppedFrames?: number;
}

interface DemoStats {
  attempted: number;
  succeeded: number;
  failed: number;
  queueDepth: number | null;
  acceptedFrames: number | null;
  droppedFrames: number | null;
}

const FRAME_INTERVAL_MS = 400;
const DUMMY_VIDEO_URL = "/demo/presentation-dummy.mp4";
const INITIAL_STATS: DemoStats = {
  attempted: 0,
  succeeded: 0,
  failed: 0,
  queueDepth: null,
  acceptedFrames: null,
  droppedFrames: null,
};

function createSessionId(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }

  return `presentation-${Date.now()}-${Math.random()
    .toString(16)
    .slice(2)}`;
}

function modeLabel(mode: DemoMode): string {
  if (mode === "PHONE") {
    return "스마트폰 실시간";
  }

  if (mode === "DUMMY") {
    return "비상용 더미영상";
  }

  return "대기";
}

function formatTime(value: number | null): string {
  return value === null
    ? "-"
    : new Date(value).toLocaleTimeString("ko-KR");
}

function toJpeg(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) {
          resolve(blob);
          return;
        }

        reject(new Error("JPEG 프레임 생성에 실패했습니다."));
      },
      "image/jpeg",
      0.82,
    );
  });
}

function parseIngestResponse(value: unknown): IngestResponse {
  return typeof value === "object" && value !== null
    ? (value as IngestResponse)
    : {};
}

export function DemoModeConsole() {
  const phoneVideoRef = useRef<HTMLVideoElement | null>(null);
  const dummyVideoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);
  const postingRef = useRef(false);
  const activeModeRef = useRef<DemoMode>("IDLE");
  const generationRef = useRef(0);

  const [mode, setMode] = useState<DemoMode>("IDLE");
  const [busy, setBusy] = useState(false);
  const [droneId, setDroneId] = useState(1);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [lastSuccessAt, setLastSuccessAt] = useState<number | null>(
    null,
  );
  const [stats, setStats] = useState<DemoStats>(INITIAL_STATS);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState(
    "발표 전 스마트폰과 더미영상 모드를 각각 한 번씩 점검하세요.",
  );
  const [dummyAvailable, setDummyAvailable] = useState<
    boolean | null
  >(null);
  const [aiHealthy, setAiHealthy] = useState<boolean | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const running = mode !== "IDLE";

  const stopMode = useCallback(
    (message = "입력 모드를 중지했습니다.") => {
      generationRef.current += 1;
      activeModeRef.current = "IDLE";
      postingRef.current = false;

      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }

      for (const track of streamRef.current?.getTracks() ?? []) {
        track.stop();
      }
      streamRef.current = null;

      if (phoneVideoRef.current) {
        phoneVideoRef.current.pause();
        phoneVideoRef.current.srcObject = null;
      }

      if (dummyVideoRef.current) {
        dummyVideoRef.current.pause();
      }

      setMode("IDLE");
      setSessionId(null);
      setStartedAt(null);
      setBusy(false);
      setNotice(message);
    },
    [],
  );

  const sendFrame = useCallback(
    async ({
      video,
      sourceId,
      currentSessionId,
      selectedDroneId,
      expectedMode,
      generation,
    }: {
      video: HTMLVideoElement;
      sourceId: string;
      currentSessionId: string;
      selectedDroneId: number;
      expectedMode: DemoMode;
      generation: number;
    }) => {
      if (
        postingRef.current ||
        activeModeRef.current !== expectedMode ||
        generationRef.current !== generation ||
        video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA ||
        video.videoWidth <= 0 ||
        video.videoHeight <= 0
      ) {
        return;
      }

      const canvas = canvasRef.current;
      if (!canvas) {
        return;
      }

      postingRef.current = true;
      setStats((current) => ({
        ...current,
        attempted: current.attempted + 1,
      }));

      try {
        const scale = Math.min(1, 960 / video.videoWidth);
        canvas.width = Math.max(
          1,
          Math.round(video.videoWidth * scale),
        );
        canvas.height = Math.max(
          1,
          Math.round(video.videoHeight * scale),
        );

        const context = canvas.getContext("2d");
        if (!context) {
          throw new Error("Canvas 2D 컨텍스트를 사용할 수 없습니다.");
        }

        context.drawImage(
          video,
          0,
          0,
          canvas.width,
          canvas.height,
        );

        const jpeg = await toJpeg(canvas);
        const query = new URLSearchParams({
          droneId: String(selectedDroneId),
          sourceId,
          sessionId: currentSessionId,
          capturedAt: new Date().toISOString(),
        });

        const response = await fetch(
          `/api/ai/ingest/frame?${query.toString()}`,
          {
            method: "POST",
            headers: {
              "Content-Type": "image/jpeg",
            },
            body: jpeg,
            cache: "no-store",
          },
        );

        if (!response.ok) {
          throw new Error(
            `프레임 전송 실패: ${response.status} ${(
              await response.text()
            ).slice(0, 240)}`,
          );
        }

        const payload = parseIngestResponse(
          await response.json(),
        );

        if (
          activeModeRef.current !== expectedMode ||
          generationRef.current !== generation
        ) {
          return;
        }

        setLastSuccessAt(Date.now());
        setError(null);
        setStats((current) => ({
          attempted: current.attempted,
          succeeded: current.succeeded + 1,
          failed: current.failed,
          queueDepth:
            typeof payload.queueDepth === "number"
              ? payload.queueDepth
              : current.queueDepth,
          acceptedFrames:
            typeof payload.acceptedFrames === "number"
              ? payload.acceptedFrames
              : current.acceptedFrames,
          droppedFrames:
            typeof payload.droppedFrames === "number"
              ? payload.droppedFrames
              : current.droppedFrames,
        }));
      } catch (caught) {
        if (
          activeModeRef.current === expectedMode &&
          generationRef.current === generation
        ) {
          setStats((current) => ({
            ...current,
            failed: current.failed + 1,
          }));
          setError(
            caught instanceof Error
              ? caught.message
              : "프레임 전송 중 오류가 발생했습니다.",
          );
        }
      } finally {
        postingRef.current = false;
      }
    },
    [],
  );

  const startCaptureLoop = useCallback(
    ({
      video,
      sourceId,
      currentSessionId,
      selectedDroneId,
      expectedMode,
    }: {
      video: HTMLVideoElement;
      sourceId: string;
      currentSessionId: string;
      selectedDroneId: number;
      expectedMode: DemoMode;
    }) => {
      const generation = generationRef.current;
      const capture = () => {
        void sendFrame({
          video,
          sourceId,
          currentSessionId,
          selectedDroneId,
          expectedMode,
          generation,
        });
      };

      capture();
      timerRef.current = window.setInterval(
        capture,
        FRAME_INTERVAL_MS,
      );
    },
    [sendFrame],
  );

  const confirmSwitch = useCallback(
    (target: string): boolean => {
      if (!running) {
        return true;
      }

      return window.confirm(
        `현재 ${modeLabel(
          mode,
        )} 모드를 중지하고 ${target} 모드로 전환하시겠습니까?`,
      );
    },
    [mode, running],
  );

  const startPhone = useCallback(async () => {
    if (!confirmSwitch("스마트폰 실시간")) {
      return;
    }

    stopMode("스마트폰 카메라를 준비하고 있습니다.");
    setBusy(true);
    setError(null);
    setStats(INITIAL_STATS);
    setLastSuccessAt(null);

    try {
      if (!window.isSecureContext) {
        throw new Error(
          "스마트폰 실시간 모드는 HTTPS 접속에서만 사용할 수 있습니다.",
        );
      }

      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("이 브라우저는 카메라 입력을 지원하지 않습니다.");
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });
      const video = phoneVideoRef.current;

      if (!video) {
        for (const track of stream.getTracks()) {
          track.stop();
        }
        throw new Error("카메라 미리보기 요소가 없습니다.");
      }

      streamRef.current = stream;
      video.srcObject = stream;
      await video.play();

      const nextSessionId = createSessionId();
      generationRef.current += 1;
      activeModeRef.current = "PHONE";
      setMode("PHONE");
      setSessionId(nextSessionId);
      setStartedAt(Date.now());
      setNotice(
        "스마트폰 실시간 추론 중입니다. 5초 이상 전송이 끊기면 더미영상으로 전환하세요.",
      );

      startCaptureLoop({
        video,
        sourceId: "presentation-phone-001",
        currentSessionId: nextSessionId,
        selectedDroneId: droneId,
        expectedMode: "PHONE",
      });
    } catch (caught) {
      stopMode("스마트폰 모드를 시작하지 못했습니다.");
      setError(
        caught instanceof Error
          ? caught.message
          : "스마트폰 모드 시작 오류",
      );
    } finally {
      setBusy(false);
    }
  }, [confirmSwitch, droneId, startCaptureLoop, stopMode]);

  const startDummy = useCallback(async () => {
    if (!confirmSwitch("비상용 더미영상")) {
      return;
    }

    stopMode("더미영상을 준비하고 있습니다.");
    setBusy(true);
    setError(null);
    setStats(INITIAL_STATS);
    setLastSuccessAt(null);

    try {
      if (dummyAvailable === false) {
        throw new Error("발표용 더미영상 파일을 찾을 수 없습니다.");
      }

      const video = dummyVideoRef.current;
      if (!video) {
        throw new Error("더미영상 재생 요소가 없습니다.");
      }

      video.loop = false;
      video.currentTime = 0;
      await video.play();

      const nextSessionId = createSessionId();
      generationRef.current += 1;
      activeModeRef.current = "DUMMY";
      setMode("DUMMY");
      setSessionId(nextSessionId);
      setStartedAt(Date.now());
      setNotice(
        "노트북 로컬 더미영상을 1회 재생 중입니다. 외부 Wi-Fi에 의존하지 않습니다.",
      );

      startCaptureLoop({
        video,
        sourceId: "presentation-dummy-001",
        currentSessionId: nextSessionId,
        selectedDroneId: droneId,
        expectedMode: "DUMMY",
      });
    } catch (caught) {
      stopMode("더미영상 모드를 시작하지 못했습니다.");
      setError(
        caught instanceof Error
          ? caught.message
          : "더미영상 모드 시작 오류",
      );
    } finally {
      setBusy(false);
    }
  }, [
    confirmSwitch,
    droneId,
    dummyAvailable,
    startCaptureLoop,
    stopMode,
  ]);

  useEffect(() => {
    let cancelled = false;

    const inspect = async () => {
      try {
        const response = await fetch(DUMMY_VIDEO_URL, {
          method: "HEAD",
          cache: "no-store",
        });
        if (!cancelled) {
          setDummyAvailable(response.ok);
        }
      } catch {
        if (!cancelled) {
          setDummyAvailable(false);
        }
      }
    };

    void inspect();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const inspect = async () => {
      try {
        const response = await fetch("/api/ai/stream/status", {
          cache: "no-store",
        });
        if (!cancelled) {
          setAiHealthy(response.ok);
        }
      } catch {
        if (!cancelled) {
          setAiHealthy(false);
        }
      }
    };

    void inspect();
    const timer = window.setInterval(inspect, 5_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    return () => {
      generationRef.current += 1;
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current);
      }
      for (const track of streamRef.current?.getTracks() ?? []) {
        track.stop();
      }
    };
  }, []);

  const phoneInterrupted = useMemo(() => {
    if (mode !== "PHONE" || startedAt === null) {
      return false;
    }

    return now - (lastSuccessAt ?? startedAt) >= 5_000;
  }, [lastSuccessAt, mode, now, startedAt]);

  const sourceId =
    mode === "PHONE"
      ? "presentation-phone-001"
      : mode === "DUMMY"
        ? "presentation-dummy-001"
        : "-";

  return (
    <section className="vf-demo-mode-command__console space-y-6">
      <header className="vf-demo-mode-command__hero rounded-3xl border border-violet-200 bg-gradient-to-br from-violet-50 via-white to-blue-50 p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div>
            <p className="vf-demo-mode-command__eyebrow text-sm font-black uppercase tracking-[0.2em] text-violet-700">
              Presentation Control
            </p>
            <h1 className="vf-demo-mode-command__title mt-2 text-3xl font-black text-slate-950">
              VisionFlow 시연 모드
            </h1>
            <p className="vf-demo-mode-command__lede mt-3 max-w-3xl text-sm leading-6 text-slate-600">
              스마트폰 실시간 촬영과 네트워크 독립형 로컬 MP4
              추론을 안전하게 전환합니다. 두 입력은 동시에
              실행되지 않습니다.
            </p>
          </div>
          <div className="vf-demo-mode-command__status rounded-2xl border border-slate-200 bg-white px-5 py-4 text-right">
            <p className="text-xs font-bold text-slate-500">현재 모드</p>
            <p className="mt-1 text-lg font-black text-slate-950">
              {modeLabel(mode)}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              AI {aiHealthy === null ? "CHECKING" : aiHealthy ? "HEALTHY" : "UNAVAILABLE"}
            </p>
          </div>
        </div>
      </header>

      {phoneInterrupted && (
        <div className="rounded-2xl border-2 border-amber-400 bg-amber-50 p-5">
          <p className="text-lg font-black text-amber-950">
            스마트폰 프레임 수신이 5초 이상 중단됐습니다.
          </p>
          <button
            type="button"
            onClick={() => void startDummy()}
            className="mt-4 rounded-xl bg-amber-600 px-5 py-3 font-black text-white hover:bg-amber-700"
          >
            비상 더미영상으로 즉시 전환
          </button>
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-2">
        <ModeCard
          icon="📱"
          title="스마트폰 실시간 촬영 모드"
          description="발표 기본 모드입니다. 노트북 모바일 핫스팟 또는 신뢰 가능한 로컬 Wi-Fi에서 사용합니다."
          active={mode === "PHONE"}
          badge={mode === "PHONE" ? "ACTIVE" : "PRIMARY"}
          button="스마트폰 실시간 모드 시작"
          disabled={busy}
          onClick={() => void startPhone()}
          tone="violet"
        />
        <ModeCard
          icon="🎞️"
          title="비상용 로컬 더미영상 모드"
          description="사전 촬영 MP4를 노트북에서 1회 재생합니다. 발표장 인터넷과 외부 Wi-Fi가 없어도 동작합니다."
          active={mode === "DUMMY"}
          badge={
            dummyAvailable === true
              ? "READY"
              : dummyAvailable === false
                ? "MISSING"
                : "CHECKING"
          }
          button="비상 더미영상 1회 재생"
          disabled={busy || dummyAvailable === false}
          onClick={() => void startDummy()}
          tone="amber"
        />
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_360px]">
        <div className="overflow-hidden rounded-3xl border border-slate-200 bg-black shadow-sm">
          <div className="flex justify-between border-b border-slate-800 px-5 py-4 text-white">
            <span className="font-black">입력 영상 미리보기</span>
            <span className="text-xs text-slate-300">
              {FRAME_INTERVAL_MS}ms 간격
            </span>
          </div>
          <div className="relative aspect-video">
            <video
              ref={phoneVideoRef}
              muted
              playsInline
              className={
                mode === "PHONE"
                  ? "h-full w-full object-contain"
                  : "hidden"
              }
            />
            <video
              ref={dummyVideoRef}
              src={DUMMY_VIDEO_URL}
              muted
              playsInline
              preload="metadata"
              onEnded={() => {
                if (activeModeRef.current === "DUMMY") {
                  stopMode("더미영상 1회 재생이 완료됐습니다.");
                }
              }}
              className={
                mode === "DUMMY"
                  ? "h-full w-full object-contain"
                  : "hidden"
              }
            />
            {mode === "IDLE" && (
              <div className="absolute inset-0 flex items-center justify-center text-slate-400">
                위의 두 모드 중 하나를 시작하세요.
              </div>
            )}
          </div>
          <canvas ref={canvasRef} className="hidden" />
        </div>

        <aside className="space-y-3 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <label className="block text-xs font-black text-slate-500">
            발표 대상 드론 ID
            <input
              type="number"
              min={1}
              disabled={running}
              value={droneId}
              onChange={(event) =>
                setDroneId(
                  Math.max(1, Number(event.target.value) || 1),
                )
              }
              className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-base font-bold text-slate-900 disabled:bg-slate-100"
            />
          </label>

          <StatusRow label="입력 상태" value={modeLabel(mode)} />
          <StatusRow label="Source ID" value={sourceId} />
          <StatusRow label="세션 ID" value={sessionId ?? "-"} />
          <StatusRow label="시작 시각" value={formatTime(startedAt)} />
          <StatusRow
            label="마지막 전송 성공"
            value={formatTime(lastSuccessAt)}
          />
          <StatusRow
            label="성공/실패"
            value={`${stats.succeeded}/${stats.failed}`}
          />
          <StatusRow
            label="AI 큐"
            value={stats.queueDepth?.toString() ?? "-"}
          />
          <StatusRow
            label="AI 누적 수신/드롭"
            value={`${stats.acceptedFrames ?? "-"}/${stats.droppedFrames ?? "-"}`}
          />

          <button
            type="button"
            disabled={!running}
            onClick={() => stopMode()}
            className="w-full rounded-xl bg-slate-950 px-5 py-3 font-black text-white disabled:opacity-40"
          >
            현재 모드 중지
          </button>
        </aside>
      </div>

      <div
        data-tone={error ? "error" : "notice"}
        className={`vf-demo-mode-notice rounded-2xl border p-4 text-sm ${
          error
            ? "border-red-300 bg-red-50 text-red-800"
            : "border-blue-200 bg-blue-50 text-blue-800"
        }`}
      >
        <p className="font-black">{error ? "오류" : "운영 안내"}</p>
        <p className="mt-1 leading-6">{error ?? notice}</p>
      </div>
    </section>
  );
}

function ModeCard({
  icon,
  title,
  description,
  active,
  badge,
  button,
  disabled,
  onClick,
  tone,
}: {
  icon: string;
  title: string;
  description: string;
  active: boolean;
  badge: string;
  button: string;
  disabled: boolean;
  onClick: () => void;
  tone: "violet" | "amber";
}) {
  const activeClass =
    tone === "violet"
      ? "border-violet-500 bg-violet-50"
      : "border-amber-500 bg-amber-50";
  const buttonClass =
    tone === "violet"
      ? "bg-violet-600 hover:bg-violet-700"
      : "bg-amber-600 hover:bg-amber-700";

  return (
    <article
      className={`vf-demo-mode-command__mode-card rounded-3xl border p-6 shadow-sm ${
        active ? activeClass : "border-slate-200 bg-white"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-3xl" aria-hidden="true">
            {icon}
          </div>
          <h2 className="mt-3 text-xl font-black text-slate-950">
            {title}
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {description}
          </p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-black text-slate-700">
          {badge}
        </span>
      </div>
      <button
        type="button"
        disabled={disabled}
        onClick={onClick}
        className={`vf-demo-mode-command__mode-action mt-6 w-full rounded-xl px-5 py-4 font-black text-white transition disabled:cursor-not-allowed disabled:opacity-50 ${buttonClass}`}
      >
        {button}
      </button>
    </article>
  );
}

function StatusRow({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl bg-slate-50 px-4 py-3">
      <p className="text-xs font-bold text-slate-500">{label}</p>
      <p className="mt-1 break-all text-sm font-black text-slate-900">
        {value}
      </p>
    </div>
  );
}
