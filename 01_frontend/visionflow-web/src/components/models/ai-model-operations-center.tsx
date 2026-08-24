"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { readOperatorConsolePreferences } from "@/lib/operator-console-settings";
import { parseAiAlertList, type AiAlertItem } from "@/types/ai-alert";
import {
  parseAiIngestStatus,
  parseAiModelStatus,
  parseAiPerformanceStatus,
  parseAiStreamStatus,
  type AiIngestStatus,
  type AiModelStatus,
  type AiPerformanceStatus,
  type AiStreamStatus,
} from "@/types/ai-model-operations";

const AUTO_REFRESH_INTERVAL_MS = 30_000;

type SourceKey = "model" | "metrics" | "ingest" | "stream" | "alerts";

const SOURCE_LABELS: Record<SourceKey, string> = {
  model: "모델 정보",
  metrics: "추론 성능",
  ingest: "입력 큐",
  stream: "분석 스트림",
  alerts: "AI 경보",
};

const HEALTH_LABELS: Record<string, string> = {
  NORMAL: "정상",
  WARNING: "주의",
  CRITICAL: "긴급",
  WAITING_INPUT: "입력 대기",
  STOPPED: "중지",
};

const REASON_LABELS: Record<string, string> = {
  NO_INPUT_FRAMES: "입력 프레임 대기 중",
  PIPELINE_STOPPED: "추론 파이프라인 중지",
  STALE_PROCESSING: "최근 처리 지연",
  HIGH_P95_INFERENCE_MS: "P95 추론 지연 증가",
  LOW_PROCESSING_RATIO: "입력 대비 처리율 저하",
  HIGH_DROP_RATE: "입력 프레임 드롭 증가",
  HIGH_QUEUE_UTILIZATION: "입력 큐 사용량 증가",
  INSUFFICIENT_SAMPLES: "성능 표본 수집 중",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function errorMessage(body: unknown, fallback: string): string {
  return isRecord(body) && typeof body.message === "string" ? body.message : fallback;
}

async function fetchJson(url: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new Error(errorMessage(body, `HTTP ${response.status}`));
  return body;
}

function rejectedMessage(result: PromiseSettledResult<unknown>, fallback: string): string {
  return result.status === "rejected" && result.reason instanceof Error
    ? result.reason.message
    : fallback;
}

function formatNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("ko-KR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatDateTime(value: string | Date | null): string {
  if (!value) return "아직 수신되지 않음";
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) return "시각 확인 필요";
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

function formatBytes(value: number | null): string {
  if (value === null) return "—";
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(2)} GiB`;
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MiB`;
  return `${value.toLocaleString("ko-KR")} B`;
}

function MetricCard({ label, value, detail, accent }: { label: string; value: string; detail: string; accent: string }) {
  return (
    <article className={`vf-model-command__metric rounded-2xl border p-5 ${accent}`}>
      <p className="text-xs font-bold uppercase tracking-[0.16em] opacity-70">{label}</p>
      <p className="mt-3 break-words text-3xl font-black tabular-nums">{value}</p>
      <p className="mt-2 text-sm opacity-75">{detail}</p>
    </article>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="vf-model-command__detail rounded-xl border p-4">
      <dt className="vf-model-command__detail-label text-xs font-bold">{label}</dt>
      <dd className="vf-model-command__detail-value mt-2 break-words font-bold">{value}</dd>
    </div>
  );
}

function Panel({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <section className="vf-model-command__panel rounded-3xl border p-6">
      <h2 className="vf-model-command__panel-title text-xl font-black">{title}</h2>
      <p className="vf-model-command__panel-description mt-1 text-sm leading-6">{description}</p>
      <div className="vf-model-command__panel-body mt-6">{children}</div>
    </section>
  );
}

export function AiModelOperationsCenter() {
  const [consolePreferences] = useState(() => readOperatorConsolePreferences());
  const [autoRefresh, setAutoRefresh] = useState(
    consolePreferences.aiModelAutoRefresh,
  );
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [sourceErrors, setSourceErrors] = useState<Partial<Record<SourceKey, string>>>({});
  const [model, setModel] = useState<AiModelStatus | null>(null);
  const [metrics, setMetrics] = useState<AiPerformanceStatus | null>(null);
  const [ingest, setIngest] = useState<AiIngestStatus | null>(null);
  const [stream, setStream] = useState<AiStreamStatus | null>(null);
  const [alerts, setAlerts] = useState<AiAlertItem[]>([]);
  const requestSequence = useRef(0);
  const abortController = useRef<AbortController | null>(null);

  const refresh = useCallback(async (silent = false) => {
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    abortController.current?.abort();
    const controller = new AbortController();
    abortController.current = controller;
    if (!silent) setRefreshing(true);

    const [modelResult, metricsResult, ingestResult, streamResult, alertsResult] =
      await Promise.allSettled([
        fetchJson("/api/ai/models/status", controller.signal),
        fetchJson("/api/ai/metrics/status", controller.signal),
        fetchJson("/api/ai/ingest/status", controller.signal),
        fetchJson("/api/ai/stream/status", controller.signal),
        fetchJson("/api/ai/alerts?limit=100", controller.signal),
      ]);

    if (controller.signal.aborted || sequence !== requestSequence.current) return;

    const parsedModel = modelResult.status === "fulfilled" ? parseAiModelStatus(modelResult.value) : null;
    const parsedMetrics = metricsResult.status === "fulfilled" ? parseAiPerformanceStatus(metricsResult.value) : null;
    const parsedIngest = ingestResult.status === "fulfilled" ? parseAiIngestStatus(ingestResult.value) : null;
    const parsedStream = streamResult.status === "fulfilled" ? parseAiStreamStatus(streamResult.value) : null;
    const parsedAlerts = alertsResult.status === "fulfilled" ? parseAiAlertList(alertsResult.value) : null;
    const nextErrors: Partial<Record<SourceKey, string>> = {};

    if (parsedModel) setModel(parsedModel);
    else nextErrors.model = modelResult.status === "fulfilled" ? "모델 상태 형식이 올바르지 않습니다." : rejectedMessage(modelResult, "모델 상태 조회 실패");
    if (parsedMetrics) setMetrics(parsedMetrics);
    else nextErrors.metrics = metricsResult.status === "fulfilled" ? "성능 상태 형식이 올바르지 않습니다." : rejectedMessage(metricsResult, "성능 상태 조회 실패");
    if (parsedIngest) setIngest(parsedIngest);
    else nextErrors.ingest = ingestResult.status === "fulfilled" ? "입력 상태 형식이 올바르지 않습니다." : rejectedMessage(ingestResult, "입력 상태 조회 실패");
    if (parsedStream) setStream(parsedStream);
    else nextErrors.stream = streamResult.status === "fulfilled" ? "스트림 상태 형식이 올바르지 않습니다." : rejectedMessage(streamResult, "스트림 상태 조회 실패");
    if (parsedAlerts) setAlerts(parsedAlerts);
    else nextErrors.alerts = alertsResult.status === "fulfilled" ? "경보 목록 형식이 올바르지 않습니다." : rejectedMessage(alertsResult, "경보 목록 조회 실패");

    setSourceErrors(nextErrors);
    setLastUpdatedAt(new Date());
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void refresh(), 0);
    return () => {
      window.clearTimeout(timeoutId);
      abortController.current?.abort();
    };
  }, [refresh]);

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh(true);
    }, AUTO_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [autoRefresh, refresh]);

  const alertSummary = useMemo(() => {
    const summary = { open: 0, acknowledged: 0, resolved: 0, info: 0, warning: 0, critical: 0 };
    for (const alert of alerts) {
      if (alert.status === "OPEN") summary.open += 1;
      else if (alert.status === "ACKNOWLEDGED") summary.acknowledged += 1;
      else summary.resolved += 1;
      if (alert.severity === "INFO") summary.info += 1;
      else if (alert.severity === "WARNING") summary.warning += 1;
      else summary.critical += 1;
    }
    return summary;
  }, [alerts]);

  const healthStatus = metrics?.health.status ?? (metrics?.running ? "NORMAL" : "WAITING_INPUT");
  const healthTone = healthStatus === "CRITICAL" || healthStatus === "STOPPED"
    ? "vf-model-command__health--critical"
    : healthStatus === "WARNING"
      ? "vf-model-command__health--warning"
      : "vf-model-command__health--normal";
  const sourceFailureCount = Object.keys(sourceErrors).length;

  return (
    <div data-ai-model-command-center className="vf-model-command mx-auto max-w-[1580px] space-y-7">
      <header className="vf-model-command__hero flex flex-wrap items-end justify-between gap-5">
        <div>
          <p className="vf-model-command__eyebrow text-xs font-black uppercase tracking-[0.24em]">AI Operations Intelligence</p>
          <h1 className="vf-model-command__title mt-2 text-3xl font-black tracking-tight sm:text-4xl">AI 모델 운영 센터</h1>
          <p className="vf-model-command__lede mt-3 max-w-3xl text-sm leading-6">현재 적재 모델의 출처·GPU 런타임·추론 성능·입력 큐·분석 스트림과 최근 경보를 인증된 읽기 데이터로 통합합니다.</p>
        </div>
        <div className="vf-model-command__hero-actions flex items-center gap-3">
          <label className="vf-model-command__auto-refresh flex items-center gap-2 rounded-xl border px-4 py-3 text-sm font-bold">
            <input type="checkbox" checked={autoRefresh} onChange={(event) => setAutoRefresh(event.target.checked)} />
            30초 자동 갱신
          </label>
          <button type="button" onClick={() => void refresh()} disabled={refreshing} className="vf-model-command__refresh rounded-xl px-5 py-3 text-sm font-bold disabled:opacity-50">
            {refreshing ? "갱신 중" : "지금 갱신"}
          </button>
        </div>
      </header>

      <section className="vf-model-command__summary rounded-[2rem] p-6 text-white sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.22em] text-cyan-300">Active Model Summary</p>
            <h2 className="mt-2 text-2xl font-black">현재 AI 런타임</h2>
          </div>
          <span className={`vf-model-command__health rounded-full border px-4 py-2 text-sm font-bold ${healthTone}`}>{HEALTH_LABELS[healthStatus] ?? healthStatus}</span>
        </div>
        <div className="mt-7 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard label="Active Model" value={model?.profile ?? metrics?.modelName ?? "—"} detail={model?.localFile ? "검증된 로컬 모델" : "모델 상태 확인 필요"} accent="border-cyan-400/25 bg-cyan-500/10" />
          <MetricCard label="Compute Device" value={model?.cudaDeviceName ?? model?.deviceEffective ?? metrics?.device ?? "—"} detail={model?.cudaAvailable ? `CUDA 장치 ${model.cudaDeviceCount}개` : "CUDA 상태 확인 필요"} accent="border-violet-400/25 bg-violet-500/10" />
          <MetricCard label="Processing FPS" value={formatNumber(metrics?.processingFps, 1)} detail={`입력 ${formatNumber(ingest?.inputFps, 1)} FPS`} accent="border-sky-400/25 bg-sky-500/10" />
          <MetricCard label="P95 Inference" value={metrics ? `${formatNumber(metrics.p95InferenceMs, 1)}ms` : "—"} detail={`평균 ${formatNumber(metrics?.averageInferenceMs, 1)}ms`} accent="border-emerald-400/25 bg-emerald-500/10" />
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-2" aria-live="polite">
          {(Object.keys(SOURCE_LABELS) as SourceKey[]).map((key) => (
            <span key={key} title={sourceErrors[key]} className={`vf-model-command__source-chip rounded-full border px-3 py-1.5 text-xs font-bold ${sourceErrors[key] ? "vf-model-command__source-chip--degraded" : "vf-model-command__source-chip--healthy"}`}>
              {SOURCE_LABELS[key]} · {sourceErrors[key] ? "이전 정상값" : "정상"}
            </span>
          ))}
          <span className="vf-model-command__timestamp ml-auto text-xs">{formatDateTime(lastUpdatedAt)} 갱신</span>
        </div>
        <p className="vf-model-command__summary-message mt-4 text-sm">{sourceFailureCount > 0 ? `${sourceFailureCount}개 소스에 부분 장애가 있어 마지막 정상 데이터를 유지합니다.` : "다섯 개 소스가 모두 정상이며 최신 검증 데이터를 표시합니다."}</p>
      </section>

      {loading && !model && !metrics ? (
        <div className="vf-model-command__loading rounded-3xl border p-10 text-center font-semibold">AI 모델 운영 데이터를 불러오고 있습니다.</div>
      ) : (
        <div className="grid gap-7 xl:grid-cols-2">
          <Panel title="모델 신원과 판정 설정" description="민감한 호스트 경로는 제외하고 모델 해시·크기·클래스와 추론 임계값만 표시합니다.">
            <dl className="grid gap-3 sm:grid-cols-2">
              <Detail label="프로필" value={model?.profile ?? "—"} />
              <Detail label="SHA-256" value={model?.sha256 ? `${model.sha256.slice(0, 16)}…${model.sha256.slice(-8)}` : "—"} />
              <Detail label="파일 크기" value={formatBytes(model?.sizeBytes ?? null)} />
              <Detail label="클래스 수" value={`${formatNumber(model?.classCount)}개`} />
              <Detail label="Confidence" value={model?.confidence === null || model?.confidence === undefined ? "—" : `${(model.confidence * 100).toFixed(0)}%`} />
              <Detail label="IOU · 입력 크기" value={`${formatNumber(model?.iou, 2)} · ${formatNumber(model?.imageSize)}px`} />
            </dl>
            <div className="mt-4 flex flex-wrap gap-2">
              {model?.classes.map((item) => <span key={item.id} className="vf-model-command__class-chip rounded-full px-3 py-1.5 text-xs font-bold">{item.id} · {item.name}</span>)}
              {model && model.classes.length === 0 ? <span className="text-sm text-slate-500">등록된 클래스가 없습니다.</span> : null}
            </div>
          </Panel>

          <Panel title="GPU와 실행 환경" description="실제 적용 장치와 PyTorch·CUDA·cuDNN 런타임을 교차 확인합니다.">
            <dl className="grid gap-3 sm:grid-cols-2">
              <Detail label="적용 장치" value={model?.deviceEffective ?? metrics?.device ?? "—"} />
              <Detail label="GPU" value={model?.cudaDeviceName ?? "—"} />
              <Detail label="CUDA 가용성" value={model?.cudaAvailable ? "사용 가능" : "사용 불가 또는 미확인"} />
              <Detail label="Compute Capability" value={model?.cudaCapability.length ? model.cudaCapability.join(".") : "—"} />
              <Detail label="GPU 메모리" value={formatBytes(model?.cudaTotalMemoryBytes ?? null)} />
              <Detail label="CUDA 필수" value={model?.requireCuda ? "필수" : "선택"} />
              <Detail label="PyTorch" value={model?.torchVersion ?? "—"} />
              <Detail label="CUDA · cuDNN" value={`${model?.torchCudaVersion ?? "—"} · ${formatNumber(model?.cudnnVersion)}`} />
            </dl>
          </Panel>

          <Panel title="추론 처리 성능" description="누적 처리량과 짧은 롤링 창의 FPS·지연 상태입니다.">
            <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Detail label="처리 프레임" value={formatNumber(metrics?.processedFrames)} />
              <Detail label="탐지 프레임" value={formatNumber(metrics?.detectedFrames)} />
              <Detail label="총 탐지" value={formatNumber(metrics?.totalDetections)} />
              <Detail label="평균 추론" value={metrics ? `${formatNumber(metrics.averageInferenceMs, 1)}ms` : "—"} />
              <Detail label="P95 · 최대" value={metrics ? `${formatNumber(metrics.p95InferenceMs, 1)} · ${formatNumber(metrics.maximumInferenceMs, 1)}ms` : "—"} />
              <Detail label="롤링 표본" value={metrics ? `${metrics.rollingSampleCount}개 · ${formatNumber(metrics.rollingWindowSeconds)}초` : "—"} />
            </dl>
            <div className="vf-model-command__runtime-note mt-4 rounded-xl border p-4 text-sm">
              <p className="font-bold">{metrics?.health.reasonCodes.map((code) => REASON_LABELS[code] ?? code).join(" · ") || "성능 이상 징후 없음"}</p>
              <p className="mt-1 text-slate-500">마지막 처리 {formatDateTime(metrics?.lastProcessedAt ?? null)}</p>
            </div>
          </Panel>

          <Panel title="입력 큐와 분석 스트림" description="브라우저 입력 수용량과 최신 분석 프레임 전달 상태를 함께 봅니다.">
            <dl className="grid gap-3 sm:grid-cols-2">
              <Detail label="입력 상태" value={ingest?.running ? "실행 중" : "대기 또는 중지"} />
              <Detail label="큐" value={ingest ? `${ingest.queueDepth} / ${ingest.queueCapacity}` : "—"} />
              <Detail label="수락 · 드롭" value={ingest ? `${formatNumber(ingest.acceptedFrames)} · ${formatNumber(ingest.droppedFrames)}` : "—"} />
              <Detail label="드롭률" value={ingest ? `${formatNumber(ingest.dropRatePct, 1)}%` : "—"} />
              <Detail label="스트림" value={stream?.running ? (stream.hasFrame ? "최신 프레임 있음" : "프레임 대기") : "중지"} />
              <Detail label="연결 클라이언트" value={`${formatNumber(stream?.connectedClients)}명`} />
              <Detail label="소스 · 기체" value={stream ? `${stream.sourceId ?? "—"} · ${stream.droneId ?? "—"}` : "—"} />
              <Detail label="최신 탐지" value={stream ? `${formatNumber(stream.detectionCount)}개 · ${formatDateTime(stream.capturedAt)}` : "—"} />
            </dl>
          </Panel>

          <Panel title="최근 AI 경보 표본" description="최근 최대 100건의 운영 상태와 위험도 분포입니다. ‘정보’는 조치가 필요 없는 informational 등급입니다.">
            <dl className="grid gap-3 sm:grid-cols-3">
              <Detail label="미확인" value={`${alertSummary.open}건`} />
              <Detail label="확인" value={`${alertSummary.acknowledged}건`} />
              <Detail label="해결" value={`${alertSummary.resolved}건`} />
              <Detail label="정보" value={`${alertSummary.info}건`} />
              <Detail label="주의" value={`${alertSummary.warning}건`} />
              <Detail label="긴급" value={`${alertSummary.critical}건`} />
            </dl>
          </Panel>

          <Panel title="연결된 운영 화면" description="모델 상태를 실제 프레임·통합 이벤트·카메라 운영 문맥에서 이어서 확인합니다.">
            <div className="grid gap-3 sm:grid-cols-3">
              <Link href="/ai-preview" className="vf-model-command__link vf-model-command__link--primary rounded-xl px-4 py-4 text-center font-bold">AI 미리보기</Link>
              <Link href="/events" className="vf-model-command__link rounded-xl border px-4 py-4 text-center font-bold">이벤트 관제</Link>
              <Link href="/cameras" className="vf-model-command__link rounded-xl border px-4 py-4 text-center font-bold">카메라 운영</Link>
            </div>
          </Panel>
        </div>
      )}
    </div>
  );
}
