"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { readOperatorConsolePreferences } from "@/lib/operator-console-settings";
import { extractFleetReliabilityResponse } from "@/types/fleet-reliability";
import { parseMaintenanceMetrics } from "@/types/maintenance-metrics";
import type { OperationsDashboardData } from "@/types/operations-dashboard";
import {
  parseOperationsStatisticsAiMetrics,
  parseOperationsStatisticsDashboard,
  type OperationsStatisticsAiMetrics,
} from "@/types/operations-statistics";
import type { FleetReliabilityResponse } from "@/types/fleet-reliability";
import type { MaintenanceMetrics } from "@/types/maintenance-metrics";
import {
  STATISTICS_RANGE_OPTIONS,
  type StatisticsRangeDays,
} from "@/types/operator-console-settings";

const AUTO_REFRESH_INTERVAL_MS = 30_000;
const RANGE_OPTIONS = STATISTICS_RANGE_OPTIONS;

type RangeDays = StatisticsRangeDays;
type SourceKey = "operations" | "reliability" | "maintenance" | "ai";

const SOURCE_LABELS: Record<SourceKey, string> = {
  operations: "비행 세션",
  reliability: "함대 신뢰도",
  maintenance: "정비 운영",
  ai: "AI 런타임",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function errorMessage(body: unknown, fallback: string): string {
  return isRecord(body) && typeof body.message === "string"
    ? body.message
    : fallback;
}

async function fetchJson(url: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // JSON 본문이 없으면 HTTP 상태를 오류에 사용합니다.
  }
  if (!response.ok) {
    throw new Error(errorMessage(body, `HTTP ${response.status}`));
  }
  return body;
}

function rejectedMessage(
  result: PromiseSettledResult<unknown>,
  fallback: string,
): string {
  return result.status === "rejected" && result.reason instanceof Error
    ? result.reason.message
    : fallback;
}

function percent(part: number, total: number): number | null {
  return total > 0 ? Math.round((part / total) * 1_000) / 10 : null;
}

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${value.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}%`;
}

function formatNumber(value: number | null, digits = 0): string {
  if (value === null) return "—";
  return value.toLocaleString("ko-KR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatDateTime(value: string | Date | null): string {
  if (!value) return "아직 갱신되지 않음";
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

function KpiCard({
  eyebrow,
  value,
  detail,
  accent,
}: {
  eyebrow: string;
  value: string;
  detail: string;
  accent: string;
}) {
  return (
    <article className={`vf-statistics-command__kpi rounded-2xl border p-5 ${accent}`}>
      <p className="text-xs font-bold uppercase tracking-[0.16em] opacity-70">
        {eyebrow}
      </p>
      <p className="mt-3 text-3xl font-black tabular-nums">{value}</p>
      <p className="mt-2 text-sm opacity-75">{detail}</p>
    </article>
  );
}

function DistributionBar({
  label,
  value,
  total,
  color,
}: {
  label: string;
  value: number;
  total: number;
  color: string;
}) {
  const ratio = total > 0 ? Math.min(100, (value / total) * 100) : 0;
  return (
    <div className="vf-statistics-command__distribution">
      <div className="vf-statistics-command__distribution-label mb-2 flex items-center justify-between gap-4 text-sm">
        <span className="font-semibold text-slate-700">{label}</span>
        <span className="font-bold tabular-nums text-slate-950">
          {value.toLocaleString("ko-KR")}건
        </span>
      </div>
      <div className="vf-statistics-command__distribution-track h-2.5 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${ratio}%` }} />
      </div>
    </div>
  );
}

function Panel({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="vf-statistics-command__panel rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="vf-statistics-command__panel-header flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="vf-statistics-command__panel-title text-xl font-black text-slate-950">{title}</h2>
          <p className="vf-statistics-command__panel-description mt-1 text-sm leading-6 text-slate-500">{description}</p>
        </div>
        {action}
      </div>
      <div className="vf-statistics-command__panel-body mt-6">{children}</div>
    </section>
  );
}

export function OperationsStatisticsCenter() {
  const [consolePreferences] = useState(() => readOperatorConsolePreferences());
  const [rangeDays, setRangeDays] = useState<RangeDays>(
    consolePreferences.statisticsRangeDays,
  );
  const [autoRefresh, setAutoRefresh] = useState(
    consolePreferences.statisticsAutoRefresh,
  );
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [sourceErrors, setSourceErrors] = useState<Partial<Record<SourceKey, string>>>({});
  const [operations, setOperations] = useState<OperationsDashboardData | null>(null);
  const [reliability, setReliability] = useState<FleetReliabilityResponse | null>(null);
  const [maintenance, setMaintenance] = useState<MaintenanceMetrics | null>(null);
  const [aiMetrics, setAiMetrics] = useState<OperationsStatisticsAiMetrics | null>(null);
  const requestSequence = useRef(0);
  const abortController = useRef<AbortController | null>(null);

  const refresh = useCallback(async (silent = false) => {
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    abortController.current?.abort();
    const controller = new AbortController();
    abortController.current = controller;
    if (!silent) setRefreshing(true);

    const from = new Date(Date.now() - rangeDays * 24 * 60 * 60 * 1_000).toISOString();
    const [operationsResult, reliabilityResult, maintenanceResult, aiResult] =
      await Promise.allSettled([
        fetchJson(
          `/api/dashboard/operations?limit=20&from=${encodeURIComponent(from)}`,
          controller.signal,
        ),
        fetchJson("/api/flight-quality/fleet-reliability?limitPerDrone=20", controller.signal),
        fetchJson(`/api/maintenance/metrics?windowDays=${rangeDays}`, controller.signal),
        fetchJson("/api/ai/metrics/status", controller.signal),
      ]);

    if (controller.signal.aborted || sequence !== requestSequence.current) return;

    const parsedOperations = operationsResult.status === "fulfilled"
      ? parseOperationsStatisticsDashboard(operationsResult.value)
      : null;
    const parsedReliability = reliabilityResult.status === "fulfilled"
      ? extractFleetReliabilityResponse(reliabilityResult.value)
      : null;
    const parsedMaintenance = maintenanceResult.status === "fulfilled"
      ? parseMaintenanceMetrics(maintenanceResult.value)
      : null;
    const parsedAi = aiResult.status === "fulfilled"
      ? parseOperationsStatisticsAiMetrics(aiResult.value)
      : null;
    const nextErrors: Partial<Record<SourceKey, string>> = {};

    if (parsedOperations) setOperations(parsedOperations);
    else nextErrors.operations = operationsResult.status === "fulfilled"
      ? "비행 세션 통계 응답 형식이 올바르지 않습니다."
      : rejectedMessage(operationsResult, "비행 세션 통계를 조회하지 못했습니다.");

    if (parsedReliability) setReliability(parsedReliability);
    else nextErrors.reliability = reliabilityResult.status === "fulfilled"
      ? "함대 신뢰도 응답 형식이 올바르지 않습니다."
      : rejectedMessage(reliabilityResult, "함대 신뢰도를 조회하지 못했습니다.");

    if (parsedMaintenance) setMaintenance(parsedMaintenance);
    else nextErrors.maintenance = maintenanceResult.status === "fulfilled"
      ? "정비 운영 KPI 응답 형식이 올바르지 않습니다."
      : rejectedMessage(maintenanceResult, "정비 운영 KPI를 조회하지 못했습니다.");

    if (parsedAi) setAiMetrics(parsedAi);
    else nextErrors.ai = aiResult.status === "fulfilled"
      ? "AI 런타임 응답 형식이 올바르지 않습니다."
      : rejectedMessage(aiResult, "AI 런타임을 조회하지 못했습니다.");

    setSourceErrors(nextErrors);
    setLastUpdatedAt(new Date());
    setLoading(false);
    setRefreshing(false);
  }, [rangeDays]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void refresh(), 0);
    return () => {
      window.clearTimeout(timeoutId);
      abortController.current?.abort();
    };
  }, [refresh]);

  useEffect(() => {
    if (!autoRefresh) return;
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh(true);
    }, AUTO_REFRESH_INTERVAL_MS);
    const handleVisibility = () => {
      if (document.visibilityState === "visible") void refresh(true);
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [autoRefresh, refresh]);

  const sourceHealth = useMemo(
    () => (Object.keys(SOURCE_LABELS) as SourceKey[]).map((key) => ({
      key,
      label: SOURCE_LABELS[key],
      error: sourceErrors[key] ?? null,
    })),
    [sourceErrors],
  );

  const closedSessions = (operations?.flightSessions.completed ?? 0) +
    (operations?.flightSessions.aborted ?? 0);
  const completionRate = percent(
    operations?.flightSessions.completed ?? 0,
    closedSessions,
  );
  const detectionRate = percent(
    aiMetrics?.detectedFrames ?? 0,
    aiMetrics?.processedFrames ?? 0,
  );
  const failedSourceCount = sourceHealth.filter((source) => source.error).length;
  const aiHealthClass = {
    NORMAL: "bg-emerald-100 text-emerald-800",
    WARNING: "bg-amber-100 text-amber-900",
    CRITICAL: "bg-rose-100 text-rose-900",
    WAITING_INPUT: "bg-sky-100 text-sky-900",
    STOPPED: "bg-slate-200 text-slate-700",
  }[aiMetrics?.health.status ?? "STOPPED"];

  return (
    <div data-operations-statistics-center data-statistics-command-center className="vf-statistics-command mx-auto max-w-[1500px] space-y-7">
      <header className="vf-statistics-command__hero flex flex-wrap items-end justify-between gap-5">
        <div>
          <p className="vf-command-eyebrow text-xs font-black uppercase tracking-[0.24em] text-cyan-700">
            Operations intelligence
          </p>
          <h1 className="vf-statistics-command__title mt-2 text-3xl font-black tracking-tight text-slate-950 sm:text-4xl">
            운영 통계 센터
          </h1>
          <p className="vf-statistics-command__lede mt-3 max-w-3xl text-sm leading-6 text-slate-600">
            비행 세션, AI 처리, 기체 신뢰도와 정비 성과를 기존 인증된 읽기 데이터로 통합합니다.
          </p>
        </div>
        <div className="vf-statistics-command__hero-actions flex flex-wrap items-center gap-2">
          <label className="vf-statistics-command__auto-refresh flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(event) => setAutoRefresh(event.target.checked)}
              className="size-4 accent-cyan-600"
            />
            30초 자동 갱신
          </label>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={refreshing}
            className="vf-statistics-command__refresh rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-slate-800 disabled:cursor-wait disabled:opacity-60"
          >
            {refreshing ? "갱신 중" : "지금 갱신"}
          </button>
        </div>
      </header>

      <section className="vf-statistics-command__summary overflow-hidden rounded-[2rem] bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 p-6 text-white shadow-xl sm:p-8">
        <div className="vf-statistics-command__summary-header flex flex-wrap items-start justify-between gap-5">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.2em] text-cyan-300">
              Fleet performance summary
            </p>
            <h2 className="mt-2 text-2xl font-black">핵심 운영 성과</h2>
          </div>
          <div className="vf-statistics-command__range flex flex-wrap gap-2" aria-label="조회 기간">
            {RANGE_OPTIONS.map((days) => (
              <button
                key={days}
                type="button"
                aria-pressed={rangeDays === days}
                onClick={() => setRangeDays(days)}
                className={`vf-statistics-command__range-button rounded-full border px-4 py-2 text-sm font-bold transition ${
                  rangeDays === days
                    ? "vf-statistics-command__range-button--active border-cyan-300 bg-cyan-300 text-slate-950"
                    : "vf-statistics-command__range-button--idle border-white/20 bg-white/5 text-slate-200 hover:bg-white/10"
                }`}
              >
                최근 {days}일
              </button>
            ))}
          </div>
        </div>

        <div className="vf-statistics-command__kpi-grid mt-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            eyebrow="Flight completion"
            value={formatPercent(completionRate)}
            detail={`종료 세션 ${closedSessions.toLocaleString("ko-KR")}건 기준`}
            accent="border-cyan-400/30 bg-cyan-400/10 text-cyan-50"
          />
          <KpiCard
            eyebrow="Fleet quality"
            value={reliability ? `${formatNumber(reliability.fleetAverageScore, 1)}점` : "—"}
            detail={`평가 ${reliability?.assessmentCount.toLocaleString("ko-KR") ?? "—"}건 · 주의 기체 ${reliability?.attentionDroneCount ?? "—"}대`}
            accent="border-violet-400/30 bg-violet-400/10 text-violet-50"
          />
          <KpiCard
            eyebrow="AI detection"
            value={formatPercent(detectionRate)}
            detail={`처리 프레임 ${aiMetrics?.processedFrames.toLocaleString("ko-KR") ?? "—"}건 기준`}
            accent="border-fuchsia-400/30 bg-fuchsia-400/10 text-fuchsia-50"
          />
          <KpiCard
            eyebrow="Maintenance resolution"
            value={
              maintenance && maintenance.totalWorkOrders > 0
                ? formatPercent(maintenance.resolutionRatePercent)
                : "—"
            }
            detail={`최근 ${rangeDays}일 작업지시 ${maintenance?.totalWorkOrders.toLocaleString("ko-KR") ?? "—"}건`}
            accent="border-emerald-400/30 bg-emerald-400/10 text-emerald-50"
          />
        </div>

        <div className="vf-statistics-command__health-dock mt-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/10 bg-black/15 px-4 py-3">
          <div className="flex flex-wrap gap-2">
            {sourceHealth.map((source) => (
              <span
                key={source.key}
                title={source.error ?? `${source.label} 데이터 정상`}
                className={`vf-statistics-command__health-chip rounded-full border px-3 py-1.5 text-xs font-bold ${
                  source.error
                    ? "vf-statistics-command__health-chip--degraded border-amber-300/40 bg-amber-300/10 text-amber-100"
                    : "vf-statistics-command__health-chip--healthy border-emerald-300/30 bg-emerald-300/10 text-emerald-100"
                }`}
              >
                {source.label} · {source.error ? "이전 정상값" : "정상"}
              </span>
            ))}
          </div>
          <span className="text-xs font-semibold text-slate-300">
            {formatDateTime(lastUpdatedAt)} 갱신
          </span>
        </div>
        <p aria-live="polite" className="vf-statistics-command__health-message mt-3 text-xs leading-5 text-slate-300">
          {loading
            ? "네 개 운영 소스를 불러오는 중입니다."
            : failedSourceCount > 0
              ? `${failedSourceCount}개 소스에 부분 장애가 있어 마지막 정상 데이터를 유지합니다.`
              : "네 개 소스가 모두 정상이며 최신 검증 데이터를 표시합니다."}
        </p>
      </section>

      <div className="vf-statistics-command__grid grid gap-7 xl:grid-cols-2">
        <Panel
          title="비행 세션 흐름"
          description={`선택한 최근 ${rangeDays}일 동안 생성된 세션 상태 분포입니다.`}
          action={<Link href="/dashboard" className="vf-statistics-command__panel-link text-sm font-bold text-cyan-700 hover:underline">운영 대시보드 보기</Link>}
        >
          {operations ? (
            <div className="space-y-5">
              <DistributionBar label="완료" value={operations.flightSessions.completed} total={operations.flightSessions.total} color="bg-emerald-500" />
              <DistributionBar label="진행 중" value={operations.flightSessions.active} total={operations.flightSessions.total} color="bg-cyan-500" />
              <DistributionBar label="준비" value={operations.flightSessions.ready} total={operations.flightSessions.total} color="bg-violet-500" />
              <DistributionBar label="중단" value={operations.flightSessions.aborted} total={operations.flightSessions.total} color="bg-rose-500" />
              <div className="vf-statistics-command__mini-metrics grid grid-cols-3 gap-3 border-t border-slate-100 pt-5 text-center">
                <div><p className="text-xs text-slate-500">AI 이벤트</p><p className="mt-1 font-black tabular-nums">{operations.aiInference.totalEvents.toLocaleString("ko-KR")}</p></div>
                <div><p className="text-xs text-slate-500">탐지 이벤트</p><p className="mt-1 font-black tabular-nums">{operations.aiInference.detectedEvents.toLocaleString("ko-KR")}</p></div>
                <div><p className="text-xs text-slate-500">총 탐지</p><p className="mt-1 font-black tabular-nums">{operations.aiInference.totalDetections.toLocaleString("ko-KR")}</p></div>
              </div>
            </div>
          ) : <p className="vf-statistics-command__placeholder rounded-2xl bg-slate-50 p-6 text-sm text-slate-500">비행 세션 통계를 기다리고 있습니다.</p>}
        </Panel>

        <Panel
          title="AI 처리 성능"
          description="현재 AI 서버의 누적 처리량과 짧은 롤링 성능 창입니다. 선택 기간과 무관한 실시간 스냅샷입니다."
          action={<Link href="/ai-preview" className="vf-statistics-command__panel-link text-sm font-bold text-cyan-700 hover:underline">AI 미리보기</Link>}
        >
          {aiMetrics ? (
            <div>
              <div className="vf-statistics-command__runtime flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-slate-950 p-4 text-white">
                <div><p className="text-xs text-slate-400">모델 · 장치</p><p className="mt-1 font-bold">{aiMetrics.modelName} · {aiMetrics.device}</p></div>
                <span className={`rounded-full px-3 py-1.5 text-xs font-black ${aiHealthClass}`}>{aiMetrics.health.status}</span>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  ["처리 FPS", formatNumber(aiMetrics.processingFps, 1)],
                  ["평균 추론", `${formatNumber(aiMetrics.averageInferenceMs, 1)}ms`],
                  ["P95 추론", `${formatNumber(aiMetrics.p95InferenceMs, 1)}ms`],
                  ["입력 드롭", aiMetrics.ingest ? formatPercent(aiMetrics.ingest.dropRatePct) : "—"],
                ].map(([label, value]) => (
                  <div key={label} className="vf-statistics-command__metric rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <p className="text-xs font-semibold text-slate-500">{label}</p>
                    <p className="mt-2 text-lg font-black tabular-nums text-slate-950">{value}</p>
                  </div>
                ))}
              </div>
              <p className="mt-4 text-xs leading-5 text-slate-500">
                롤링 표본 {aiMetrics.rollingSampleCount.toLocaleString("ko-KR")}개 · {aiMetrics.rollingWindowSeconds.toLocaleString("ko-KR")}초 창 · 마지막 처리 {formatDateTime(aiMetrics.lastProcessedAt)}
              </p>
            </div>
          ) : <p className="vf-statistics-command__placeholder rounded-2xl bg-slate-50 p-6 text-sm text-slate-500">AI 처리 통계를 기다리고 있습니다.</p>}
        </Panel>
      </div>

      <Panel
        title="기체별 운영 신뢰도"
        description="각 기체의 최신 최대 20개 품질 평가를 비교합니다. 기간 버튼은 이 섹션의 표본 범위를 바꾸지 않습니다."
        action={<Link href="/fleet-reliability" className="vf-statistics-command__panel-link text-sm font-bold text-cyan-700 hover:underline">신뢰도 상세 보기</Link>}
      >
        {reliability?.drones.length ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {reliability.drones.map((drone) => (
              <article key={drone.droneId} className="vf-statistics-command__drone rounded-2xl border border-slate-200 p-5">
                <div className="flex items-start justify-between gap-3">
                  <div><p className="font-black text-slate-950">{drone.droneName ?? `Drone #${drone.droneId}`}</p><p className="mt-1 text-xs text-slate-500">{drone.droneCode ?? `ID ${drone.droneId}`}</p></div>
                  <span className={`rounded-full px-3 py-1 text-xs font-black ${drone.status === "STABLE" ? "bg-emerald-100 text-emerald-800" : drone.status === "WATCH" ? "bg-amber-100 text-amber-900" : "bg-rose-100 text-rose-900"}`}>{drone.status}</span>
                </div>
                <div className="mt-5 flex items-end justify-between gap-4">
                  <div><p className="text-xs text-slate-500">평균 품질 점수</p><p className="mt-1 text-3xl font-black tabular-nums">{formatNumber(drone.averageScore, 1)}</p></div>
                  <div className="flex h-12 items-end gap-1" aria-label={`${drone.droneName ?? drone.droneId} 품질 추세`}>
                    {drone.trend.slice(-10).map((point) => (
                      <span key={point.sessionId} title={`${point.sessionName}: ${point.quality.score.toFixed(1)}점`} className="w-2 rounded-t bg-cyan-500" style={{ height: `${Math.max(8, Math.min(100, point.quality.score))}%` }} />
                    ))}
                  </div>
                </div>
                <p className="mt-4 text-xs text-slate-500">평가 {drone.assessmentCount}건 · 중단 {drone.abortedCount}건 · 경고 {drone.warningCount}건</p>
              </article>
            ))}
          </div>
        ) : <p className="vf-statistics-command__placeholder rounded-2xl bg-slate-50 p-6 text-sm text-slate-500">기체 신뢰도 평가를 기다리고 있습니다.</p>}
      </Panel>

      <div className="vf-statistics-command__grid grid gap-7 xl:grid-cols-2">
        <Panel
          title="정비 작업지시 성과"
          description={`최근 ${rangeDays}일 생성된 작업지시 상태와 해결 성과입니다.`}
          action={<Link href="/maintenance" className="vf-statistics-command__panel-link text-sm font-bold text-cyan-700 hover:underline">정비 관제 보기</Link>}
        >
          {maintenance ? (
            <div className="space-y-5">
              <DistributionBar label="완료" value={maintenance.completedWorkOrders} total={maintenance.totalWorkOrders} color="bg-emerald-500" />
              <DistributionBar label="진행 중" value={maintenance.inProgressWorkOrders} total={maintenance.totalWorkOrders} color="bg-cyan-500" />
              <DistributionBar label="접수" value={maintenance.openWorkOrders} total={maintenance.totalWorkOrders} color="bg-violet-500" />
              <DistributionBar label="운항 중지" value={maintenance.groundedWorkOrders} total={maintenance.totalWorkOrders} color="bg-rose-500" />
              <div className="vf-statistics-command__mini-metrics grid grid-cols-2 gap-3 border-t border-slate-100 pt-5">
                <div className="vf-statistics-command__metric rounded-xl bg-slate-50 p-4"><p className="text-xs text-slate-500">평균 시작 지연</p><p className="mt-1 font-black">{maintenance.averageStartDelayMinutes === null ? "—" : `${maintenance.averageStartDelayMinutes}분`}</p></div>
                <div className="vf-statistics-command__metric rounded-xl bg-slate-50 p-4"><p className="text-xs text-slate-500">평균 해결 시간</p><p className="mt-1 font-black">{maintenance.averageResolutionMinutes === null ? "—" : `${maintenance.averageResolutionMinutes}분`}</p></div>
              </div>
            </div>
          ) : <p className="vf-statistics-command__placeholder rounded-2xl bg-slate-50 p-6 text-sm text-slate-500">정비 성과 통계를 기다리고 있습니다.</p>}
        </Panel>

        <Panel title="함대 비행 허가" description="정비 비행 게이트의 현재 함대 판정입니다. 기간과 무관한 최신 상태입니다.">
          {maintenance ? (
            <div>
              <div className="vf-statistics-command__gate-header flex items-center justify-between rounded-2xl bg-slate-950 p-5 text-white">
                <div><p className="text-xs text-slate-400">게이트 모드</p><p className="mt-1 text-2xl font-black">{maintenance.gateMode}</p></div>
                <span className="rounded-full bg-cyan-300 px-3 py-1.5 text-xs font-black text-slate-950">전체 {maintenance.totalDrones}대</span>
              </div>
              <div className="vf-statistics-command__gate-grid mt-4 grid grid-cols-3 gap-3 text-center">
                <div className="vf-statistics-command__gate vf-statistics-command__gate--allowed rounded-2xl border border-emerald-200 bg-emerald-50 p-4"><p className="text-xs font-bold text-emerald-700">비행 가능</p><p className="mt-2 text-2xl font-black text-emerald-900">{maintenance.allowedDrones}대</p></div>
                <div className="vf-statistics-command__gate vf-statistics-command__gate--attention rounded-2xl border border-amber-200 bg-amber-50 p-4"><p className="text-xs font-bold text-amber-700">점검 주의</p><p className="mt-2 text-2xl font-black text-amber-900">{maintenance.attentionDrones}대</p></div>
                <div className="vf-statistics-command__gate vf-statistics-command__gate--blocked rounded-2xl border border-rose-200 bg-rose-50 p-4"><p className="text-xs font-bold text-rose-700">비행 차단</p><p className="mt-2 text-2xl font-black text-rose-900">{maintenance.blockedDrones}대</p></div>
              </div>
              <p className="mt-4 text-xs leading-5 text-slate-500">최신 정비 판정 {formatDateTime(maintenance.generatedAt)} · 이 화면에서는 판정을 변경하지 않습니다.</p>
            </div>
          ) : <p className="vf-statistics-command__placeholder rounded-2xl bg-slate-50 p-6 text-sm text-slate-500">함대 비행 허가 통계를 기다리고 있습니다.</p>}
        </Panel>
      </div>
    </div>
  );
}
