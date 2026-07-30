"use client";

import { useEffect, useState } from "react";

interface AiIngestMetrics {
  enabled: boolean;
  running: boolean;
  queueDepth: number;
  queueCapacity: number;
  acceptedFrames: number;
  droppedFrames: number;
  dropRatePct: number;
  inputFps: number;
  lastReceivedAt: string | null;
}

interface AiStreamMetrics {
  running: boolean;
  connectedClients: number;
  hasFrame: boolean;
}

type AiPerformanceHealthStatus =
  | "NORMAL"
  | "WARNING"
  | "CRITICAL"
  | "WAITING_INPUT"
  | "STOPPED";

interface AiPerformanceHealth {
  status: AiPerformanceHealthStatus;
  reasonCodes: string[];
  inputToProcessingRatio: number | null;
  queueUtilizationPct: number;
}

interface AiPerformanceMetrics {
  running: boolean;
  modelName: string;
  device: string;
  sourceType: string;
  configuredInputFps: number;
  processedFrames: number;
  detectedFrames: number;
  totalDetections: number;
  processingFps: number;
  averageInferenceMs: number;
  p95InferenceMs: number;
  maximumInferenceMs: number;
  rollingSampleCount: number;
  rollingWindowSeconds: number;
  lastProcessedAt: string | null;
  ingest: AiIngestMetrics | null;
  stream: AiStreamMetrics;
  health: AiPerformanceHealth;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isAiIngestMetrics(value: unknown): value is AiIngestMetrics {
  return (
    isRecord(value) &&
    typeof value.enabled === "boolean" &&
    typeof value.running === "boolean" &&
    typeof value.queueDepth === "number" &&
    typeof value.queueCapacity === "number" &&
    typeof value.acceptedFrames === "number" &&
    typeof value.droppedFrames === "number" &&
    typeof value.dropRatePct === "number" &&
    typeof value.inputFps === "number"
  );
}

function isAiStreamMetrics(value: unknown): value is AiStreamMetrics {
  return (
    isRecord(value) &&
    typeof value.running === "boolean" &&
    typeof value.connectedClients === "number" &&
    typeof value.hasFrame === "boolean"
  );
}

function isAiPerformanceHealth(value: unknown): value is AiPerformanceHealth {
  if (!isRecord(value) || !Array.isArray(value.reasonCodes)) {
    return false;
  }

  const statuses: AiPerformanceHealthStatus[] = [
    "NORMAL",
    "WARNING",
    "CRITICAL",
    "WAITING_INPUT",
    "STOPPED",
  ];

  return (
    typeof value.status === "string" &&
    statuses.includes(value.status as AiPerformanceHealthStatus) &&
    value.reasonCodes.every((reason) => typeof reason === "string") &&
    (value.inputToProcessingRatio === null ||
      typeof value.inputToProcessingRatio === "number") &&
    typeof value.queueUtilizationPct === "number"
  );
}

function isAiPerformanceMetrics(value: unknown): value is AiPerformanceMetrics {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.running === "boolean" &&
    typeof value.modelName === "string" &&
    typeof value.device === "string" &&
    typeof value.sourceType === "string" &&
    typeof value.configuredInputFps === "number" &&
    typeof value.processedFrames === "number" &&
    typeof value.detectedFrames === "number" &&
    typeof value.processingFps === "number" &&
    typeof value.averageInferenceMs === "number" &&
    typeof value.p95InferenceMs === "number" &&
    typeof value.maximumInferenceMs === "number" &&
    typeof value.totalDetections === "number" &&
    typeof value.rollingSampleCount === "number" &&
    typeof value.rollingWindowSeconds === "number" &&
    (value.ingest === null || isAiIngestMetrics(value.ingest)) &&
    isAiStreamMetrics(value.stream) &&
    isAiPerformanceHealth(value.health)
  );
}

const HEALTH_REASON_LABELS: Record<string, string> = {
  PIPELINE_STOPPED: "AI 추론 파이프라인이 중지되었습니다.",
  NO_INPUT_FRAMES: "아직 수신된 영상 프레임이 없습니다.",
  INPUT_STALE: "최근 영상 입력이 없어 대기 상태로 전환되었습니다.",
  PROCESSING_STALLED: "영상 입력은 있으나 추론 처리가 멈췄습니다.",
  P95_LATENCY_WARNING: "P95 추론 지연이 주의 기준을 초과했습니다.",
  P95_LATENCY_CRITICAL: "P95 추론 지연이 위험 기준을 초과했습니다.",
  PROCESSING_RATIO_WARNING: "입력 FPS 대비 처리 FPS가 부족합니다.",
  PROCESSING_RATIO_CRITICAL: "추론 처리량이 입력 속도를 크게 밑돌고 있습니다.",
  DROP_RATE_WARNING: "입력 프레임 드롭률이 주의 기준을 초과했습니다.",
  DROP_RATE_CRITICAL: "입력 프레임 드롭률이 위험 기준을 초과했습니다.",
  QUEUE_PRESSURE: "영상 입력 큐가 많이 차 있습니다.",
  QUEUE_FULL: "영상 입력 큐가 가득 찼습니다.",
};

function healthPresentation(status: AiPerformanceHealthStatus) {
  return {
    NORMAL: {
      label: "정상",
      className: "bg-emerald-100 text-emerald-800",
      messageClassName: "border-emerald-200 bg-emerald-50 text-emerald-800",
    },
    WARNING: {
      label: "주의",
      className: "bg-amber-100 text-amber-800",
      messageClassName: "border-amber-200 bg-amber-50 text-amber-900",
    },
    CRITICAL: {
      label: "위험",
      className: "bg-rose-100 text-rose-800",
      messageClassName: "border-rose-200 bg-rose-50 text-rose-900",
    },
    WAITING_INPUT: {
      label: "영상 입력 대기",
      className: "bg-sky-100 text-sky-800",
      messageClassName: "border-sky-200 bg-sky-50 text-sky-900",
    },
    STOPPED: {
      label: "중지",
      className: "bg-slate-100 text-slate-600",
      messageClassName: "border-slate-200 bg-slate-50 text-slate-700",
    },
  }[status];
}

function number(value: number, fractionDigits = 1): string {
  return new Intl.NumberFormat("ko-KR", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

function MetricTile({
  label,
  value,
  description,
}: {
  label: string;
  value: string;
  description: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-2 text-2xl font-bold tabular-nums text-slate-950">
        {value}
      </div>
      <div className="mt-1 text-xs text-slate-500">{description}</div>
    </div>
  );
}

export function AiPerformancePanel() {
  const [metrics, setMetrics] = useState<AiPerformanceMetrics | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadMetrics() {
      try {
        const response = await fetch("/api/ai/metrics/status", {
          cache: "no-store",
        });
        const payload: unknown = await response.json();

        if (!response.ok) {
          const message =
            isRecord(payload) && typeof payload.message === "string"
              ? payload.message
              : `AI 성능 API가 HTTP ${response.status}를 반환했습니다.`;
          throw new Error(message);
        }

        if (!isAiPerformanceMetrics(payload)) {
          throw new Error("AI 성능 API 응답 형식이 올바르지 않습니다.");
        }

        if (active) {
          setMetrics(payload);
          setErrorMessage(null);
        }
      } catch (error) {
        if (active) {
          setErrorMessage(
            error instanceof Error
              ? error.message
              : "AI 추론 성능을 불러오지 못했습니다.",
          );
        }
      }
    }

    void loadMetrics();
    const intervalId = window.setInterval(() => {
      void loadMetrics();
    }, 2_000);

    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, []);

  const ingest = metrics?.ingest ?? null;
  const health = metrics?.health ?? null;
  const healthView = health ? healthPresentation(health.status) : null;

  return (
    <article className="mt-6 rounded-2xl border border-violet-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900">
            AI 실시간 추론 성능
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            최근 {metrics?.rollingWindowSeconds ?? 10}초 처리량과 추론 지연을
            2초마다 갱신합니다.
          </p>
        </div>
        <div
          className={`rounded-full px-3 py-1 text-xs font-bold ${
            healthView?.className ?? "bg-slate-100 text-slate-600"
          }`}
        >
          {healthView?.label ?? "연결 확인 중"}
        </div>
      </div>

      {errorMessage && (
        <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
          {errorMessage}
        </div>
      )}

      {health && health.reasonCodes.length > 0 && healthView && (
        <div
          className={`mt-4 rounded-xl border px-4 py-3 text-sm ${healthView.messageClassName}`}
        >
          <div className="font-bold">AI 운영 상태: {healthView.label}</div>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {health.reasonCodes.map((reason) => (
              <li key={reason}>{HEALTH_REASON_LABELS[reason] ?? reason}</li>
            ))}
          </ul>
        </div>
      )}

      {metrics ? (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricTile
              label="영상 입력 FPS"
              value={number(ingest?.inputFps ?? metrics.configuredInputFps)}
              description={
                ingest
                  ? `설정 ${number(metrics.configuredInputFps)} FPS`
                  : "영상 소스 설정값"
              }
            />
            <MetricTile
              label="추론 처리 FPS"
              value={number(metrics.processingFps)}
              description={`최근 표본 ${metrics.rollingSampleCount}개`}
            />
            <MetricTile
              label="평균 / P95 지연"
              value={`${number(metrics.averageInferenceMs)} / ${number(
                metrics.p95InferenceMs,
              )} ms`}
              description={`최대 ${number(metrics.maximumInferenceMs)} ms`}
            />
            <MetricTile
              label="처리 / 탐지"
              value={`${metrics.processedFrames.toLocaleString("ko-KR")} / ${metrics.totalDetections.toLocaleString("ko-KR")}`}
              description={`탐지 프레임 ${metrics.detectedFrames.toLocaleString(
                "ko-KR",
              )}개`}
            />
          </div>

          <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 rounded-xl bg-slate-950 px-4 py-3 text-xs text-slate-200">
            <span>
              모델 <strong className="text-white">{metrics.modelName}</strong>
            </span>
            <span>
              장치 <strong className="text-white">{metrics.device}</strong>
            </span>
            <span>
              소스 <strong className="text-white">{metrics.sourceType}</strong>
            </span>
            <span>
              입력 큐 {ingest ? `${ingest.queueDepth}/${ingest.queueCapacity}` : "-"}
            </span>
            <span>
              드롭 {ingest ? `${ingest.droppedFrames} (${number(ingest.dropRatePct)}%)` : "-"}
            </span>
            <span>
              스트림 클라이언트 {metrics.stream.connectedClients}
            </span>
            <span>
              처리율{" "}
              {health?.inputToProcessingRatio === null ||
              health?.inputToProcessingRatio === undefined
                ? "-"
                : `${number(health.inputToProcessingRatio * 100)}%`}
            </span>
          </div>
        </>
      ) : (
        !errorMessage && (
          <div className="mt-4 text-sm text-slate-500">
            AI 성능 지표를 불러오는 중입니다.
          </div>
        )
      )}
    </article>
  );
}
