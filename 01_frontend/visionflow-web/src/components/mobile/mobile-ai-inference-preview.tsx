"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { getAiStreamUrl } from "@/lib/ai-stream-url";
import type { AiStreamStatus } from "@/types/ai-stream";

interface MobileAiInferencePreviewProps {
  allowPopout?: boolean;
  expectedDroneId?: number | null;
}

interface PreviewState {
  online: boolean;
  status: AiStreamStatus | null;
  error: string | null;
}

function isAiStreamStatus(value: unknown): value is AiStreamStatus {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Partial<AiStreamStatus>;

  return (
    typeof candidate.running === "boolean" &&
    typeof candidate.hasFrame === "boolean" &&
    typeof candidate.connectedClients === "number" &&
    typeof candidate.detectionCount === "number"
  );
}

function formatTime(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }

  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleTimeString("ko-KR");
}

export function MobileAiInferencePreview({
  allowPopout = true,
  expectedDroneId = null,
}: MobileAiInferencePreviewProps) {
  const [previewState, setPreviewState] = useState<PreviewState>({
    online: false,
    status: null,
    error: null,
  });
  const [streamVersion, setStreamVersion] = useState(0);
  const [imageError, setImageError] = useState(false);
  const previousOnlineRef = useRef(false);

  const baseStreamUrl = getAiStreamUrl();
  const streamUrl = useMemo(() => {
    const separator = baseStreamUrl.includes("?") ? "&" : "?";

    return `${baseStreamUrl}${separator}v=${streamVersion}`;
  }, [baseStreamUrl, streamVersion]);

  useEffect(() => {
    let active = true;

    async function loadStatus() {
      try {
        const response = await fetch("/api/ai/stream/status", {
          method: "GET",
          headers: { Accept: "application/json" },
          cache: "no-store",
        });

        if (!response.ok) {
          throw new Error(`AI 분석 상태 조회 실패: ${response.status}`);
        }

        const payload: unknown = await response.json();

        if (!isAiStreamStatus(payload)) {
          throw new Error("AI 분석 상태 응답 형식이 올바르지 않습니다.");
        }

        if (!active) {
          return;
        }

        const online = payload.running && payload.hasFrame;

        if (online && !previousOnlineRef.current) {
          setImageError(false);
          setStreamVersion((current) => current + 1);
        }

        previousOnlineRef.current = online;
        setPreviewState({ online, status: payload, error: null });
      } catch (statusError) {
        if (!active) {
          return;
        }

        previousOnlineRef.current = false;
        setPreviewState({
          online: false,
          status: null,
          error:
            statusError instanceof Error
              ? statusError.message
              : "AI 분석 영상 상태를 확인하지 못했습니다.",
        });
      }
    }

    void loadStatus();
    const intervalId = window.setInterval(() => {
      void loadStatus();
    }, 2_000);

    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, []);

  function reconnectStream() {
    setImageError(false);
    setStreamVersion((current) => current + 1);
  }

  function openPopout() {
    window.open(
      "/ai-preview",
      "visionflow-ai-preview",
      "popup=yes,width=1280,height=820,resizable=yes,scrollbars=yes",
    );
  }

  const waiting = !previewState.online || imageError;
  const streamDroneId = previewState.status?.droneId ?? null;
  const droneMismatch =
    previewState.online &&
    expectedDroneId !== null &&
    streamDroneId !== null &&
    streamDroneId !== expectedDroneId;

  return (
    <section className="vf-ai-preview overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <header className="vf-ai-preview__header flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 p-4">
        <div>
          <div className="vf-command-eyebrow">Inference Output</div>
          <div className="flex items-center gap-2">
            <h2 className="mt-1 font-black text-slate-900">
              YOLO AI 추론 영상
            </h2>
            <span
              className={`vf-ai-preview__state rounded-full px-2 py-1 text-xs font-bold ${
                previewState.online
                  ? "vf-ai-preview__state--live"
                  : "vf-ai-preview__state--offline"
              }`}
            >
              {previewState.online ? "● LIVE" : "OFFLINE"}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            AI 서버가 바운딩 박스를 합성한 실시간 영상입니다.
          </p>
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={reconnectStream}
            className="vf-ai-preview__reconnect rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold text-slate-700"
          >
            다시 연결
          </button>
          {allowPopout && (
            <button
              type="button"
              onClick={openPopout}
              className="vf-ai-preview__popout rounded-lg px-3 py-2 text-xs font-bold text-white"
            >
              AI 추론 창 열기
            </button>
          )}
        </div>
      </header>

      <div className="vf-ai-preview__viewport relative flex aspect-video items-center justify-center overflow-hidden bg-slate-950">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={streamUrl}
          alt="VisionFlow YOLO 실시간 추론 영상"
          className="h-full w-full object-contain"
          onLoad={() => setImageError(false)}
          onError={() => setImageError(true)}
        />

        {waiting && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-950/90 p-6 text-center text-sm text-slate-300">
            {previewState.error ??
              "카메라 전송을 시작하면 YOLO 추론 영상이 표시됩니다."}
          </div>
        )}
      </div>

      <dl className="vf-ai-preview__metrics grid grid-cols-2 gap-3 bg-slate-50 p-4 text-sm sm:grid-cols-4">
        <PreviewValue
          label="프레임"
          value={`#${previewState.status?.frameIndex ?? "-"}`}
        />
        <PreviewValue
          label="현재 탐지"
          value={`${previewState.status?.detectionCount ?? 0}개`}
        />
        <PreviewValue
          label="연결 드론"
          value={String(previewState.status?.droneId ?? "-")}
        />
        <PreviewValue
          label="수신 시각"
          value={formatTime(previewState.status?.capturedAt)}
        />
      </dl>

      {droneMismatch && (
        <div className="vf-ai-preview__mismatch border-t border-amber-300 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-900">
          선택 드론 ID {expectedDroneId}와 AI 영상 드론 ID {streamDroneId}가
          다릅니다. 기존 카메라 전송을 중지한 뒤 현재 비행 세션을 다시
          시작하세요.
        </div>
      )}
    </section>
  );
}

function PreviewValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="vf-ai-preview__metric">
      <dt className="text-xs font-semibold text-slate-500">{label}</dt>
      <dd className="mt-1 font-bold text-slate-900">{value}</dd>
    </div>
  );
}
