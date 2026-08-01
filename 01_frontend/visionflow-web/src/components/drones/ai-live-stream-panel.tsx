"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { getAiStreamUrl } from "@/lib/ai-stream-url";
import type { AiInferenceEvent } from "@/types/ai-inference-event";
import type { AiStreamStatus } from "@/types/ai-stream";

interface AiLiveStreamPanelProps {
  events: AiInferenceEvent[];
  onSelectDrone: (droneId: number) => void;
}

interface StreamViewState {
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

function formatTime(value: string | null): string {
  if (!value) {
    return "-";
  }

  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleTimeString("ko-KR");
}

function sourceLabel(sourceType: AiStreamStatus["sourceType"]): string {
  switch (sourceType) {
    case "SMARTPHONE_LIVE":
      return "스마트폰 라이브";
    case "DJI_LIVE":
      return "DJI 라이브";
    case "DUMMY_VIDEO":
      return "더미 영상";
    default:
      return "영상 대기 중";
  }
}

export function AiLiveStreamPanel({
  events,
  onSelectDrone,
}: AiLiveStreamPanelProps) {
  const [viewState, setViewState] = useState<StreamViewState>({
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
          headers: {
            Accept: "application/json",
          },
          cache: "no-store",
        });

        if (!response.ok) {
          throw new Error(`스트림 상태 조회 실패: ${response.status}`);
        }

        const payload: unknown = await response.json();

        if (!isAiStreamStatus(payload)) {
          throw new Error("스트림 상태 응답 형식이 올바르지 않습니다.");
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
        setViewState({
          online,
          status: payload,
          error: null,
        });
      } catch (error) {
        if (!active) {
          return;
        }

        previousOnlineRef.current = false;
        setViewState({
          online: false,
          status: null,
          error:
            error instanceof Error
              ? error.message
              : "AI 분석 영상 상태를 확인하지 못했습니다.",
        });
      }
    }

    void loadStatus();

    const timerId = window.setInterval(() => {
      void loadStatus();
    }, 2_000);

    return () => {
      active = false;
      window.clearInterval(timerId);
    };
  }, []);

  const latestDetectionEvent = useMemo(() => {
    const streamDroneId = viewState.status?.droneId;

    if (streamDroneId === null || streamDroneId === undefined) {
      return events[0] ?? null;
    }

    return events.find((event) => event.droneId === streamDroneId) ?? null;
  }, [events, viewState.status?.droneId]);

  const connectedDroneId = viewState.status?.droneId ?? null;

  function reconnectStream() {
    setImageError(false);
    setStreamVersion((current) => current + 1);
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 p-5">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-bold text-slate-900">
              AI 실시간 분석 영상
            </h2>

            <span
              className={`rounded-full px-2.5 py-1 text-xs font-bold ${
                viewState.online
                  ? "bg-red-100 text-red-700"
                  : "bg-slate-100 text-slate-600"
              }`}
            >
              {viewState.online ? "● LIVE" : "OFFLINE"}
            </span>

            <span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-semibold text-violet-700">
              {sourceLabel(viewState.status?.sourceType ?? null)}
            </span>
          </div>

          <p className="mt-1 text-sm text-slate-500">
            YOLO가 그린 바운딩 박스를 영상 프레임에 포함해 전송합니다.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {connectedDroneId !== null && (
            <button
              type="button"
              onClick={() => onSelectDrone(connectedDroneId)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700"
            >
              연결 드론 선택
            </button>
          )}

          <button
            type="button"
            onClick={reconnectStream}
            className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white"
          >
            영상 다시 연결
          </button>
        </div>
      </div>

      <div className="grid xl:grid-cols-[minmax(0,1fr)_280px]">
        <div className="relative flex aspect-video min-h-64 items-center justify-center overflow-hidden bg-slate-950">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={streamUrl}
            alt="VisionFlow YOLO 실시간 분석 영상"
            className="h-full w-full object-contain"
            onLoad={() => setImageError(false)}
            onError={() => setImageError(true)}
          />

          {(!viewState.online || imageError) && (
            <div className="absolute inset-0 flex items-center justify-center bg-slate-950/90 p-6 text-center">
              <div>
                <div className="font-semibold text-white">
                  분석 영상을 기다리는 중입니다.
                </div>
                <div className="mt-2 max-w-md text-sm text-slate-400">
                  {viewState.error ??
                    "AI 워커와 영상 입력이 실행 중인지 확인하세요."}
                </div>
              </div>
            </div>
          )}
        </div>

        <dl className="grid content-start gap-3 bg-slate-50 p-5 text-sm">
          <div>
            <dt className="text-xs font-semibold text-slate-500">
              현재 영상 프레임
            </dt>
            <dd className="mt-1 font-bold text-slate-900">
              #{viewState.status?.frameIndex ?? "-"}
            </dd>
          </div>

          <div>
            <dt className="text-xs font-semibold text-slate-500">
              현재 프레임 탐지
            </dt>
            <dd className="mt-1 font-bold text-violet-700">
              {viewState.status?.detectionCount ?? 0}개
            </dd>
          </div>

          <div>
            <dt className="text-xs font-semibold text-slate-500">
              최근 이벤트 프레임
            </dt>
            <dd className="mt-1 font-bold text-slate-900">
              #{latestDetectionEvent?.frameIndex ?? "-"}
            </dd>
          </div>

          <div>
            <dt className="text-xs font-semibold text-slate-500">
              연결 드론 ID
            </dt>
            <dd className="mt-1 font-bold text-slate-900">
              {viewState.status?.droneId ?? "-"}
            </dd>
          </div>

          <div>
            <dt className="text-xs font-semibold text-slate-500">
              프레임 수신 시각
            </dt>
            <dd className="mt-1 font-medium text-slate-700">
              {formatTime(viewState.status?.capturedAt ?? null)}
            </dd>
          </div>

          <div>
            <dt className="text-xs font-semibold text-slate-500">
              웹 시청 연결
            </dt>
            <dd className="mt-1 font-medium text-slate-700">
              {viewState.status?.connectedClients ?? 0}개
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
