"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { formatKoreanDateTime } from "@/lib/date";
import {
  parseMaintenanceFleetFlightClearance,
  type MaintenanceFleetFlightClearance,
} from "@/types/maintenance-flight-clearance";
import {
  parseMaintenanceSlaIncidentTracking,
  type MaintenanceSlaIncidentTracking,
  type MaintenanceSlaIncidentTrackingItem,
} from "@/types/maintenance-sla-incident-tracking";

const AUTO_REFRESH_MS = 30_000;

const stageDefinitions = [
  {
    key: "OPEN",
    label: "신규 접수",
    description: "점검 시작 대기",
    accent: "bg-cyan-400",
  },
  {
    key: "IN_PROGRESS",
    label: "점검 진행",
    description: "현장 확인·조치",
    accent: "bg-sky-400",
  },
  {
    key: "SLA_RESPONSE",
    label: "SLA 대응",
    description: "Incident 조치",
    accent: "bg-violet-400",
  },
  {
    key: "DECIDED",
    label: "운항 판정",
    description: "승인 또는 중지",
    accent: "bg-emerald-400",
  },
] as const;

const slaLabels = {
  OVERDUE: "SLA 초과",
  DUE_SOON: "SLA 임박",
  ON_TRACK: "정상 추적",
  NOT_APPLICABLE: "SLA 제외",
} as const;

const slaStyles = {
  OVERDUE: "border-rose-300/40 bg-rose-400/15 text-rose-100",
  DUE_SOON: "border-amber-300/40 bg-amber-400/15 text-amber-100",
  ON_TRACK: "border-sky-300/40 bg-sky-400/15 text-sky-100",
  NOT_APPLICABLE: "border-slate-400/40 bg-slate-400/15 text-slate-200",
} as const;

interface MaintenanceMissionControlProps {
  refreshKey: number;
}

interface MissionStage {
  key: (typeof stageDefinitions)[number]["key"];
  label: string;
  description: string;
  accent: string;
  count: number;
}

export function MaintenanceMissionControl({
  refreshKey,
}: MaintenanceMissionControlProps) {
  const [tracking, setTracking] =
    useState<MaintenanceSlaIncidentTracking | null>(null);
  const [fleetClearance, setFleetClearance] =
    useState<MaintenanceFleetFlightClearance | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshRevision, setRefreshRevision] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    async function loadMissionControl(): Promise<void> {
      try {
        const [trackingResponse, clearanceResponse] = await Promise.all([
          fetch("/api/maintenance/sla/incidents", {
            headers: { Accept: "application/json" },
            cache: "no-store",
            signal: controller.signal,
          }),
          fetch("/api/maintenance/flight-clearance", {
            headers: { Accept: "application/json" },
            cache: "no-store",
            signal: controller.signal,
          }),
        ]);
        if (!trackingResponse.ok) {
          throw new Error(
            `정비 작전 현황 조회 실패: HTTP ${trackingResponse.status}`,
          );
        }
        if (!clearanceResponse.ok) {
          throw new Error(
            `함대 비행 준비 상태 조회 실패: HTTP ${clearanceResponse.status}`,
          );
        }

        const [trackingBody, clearanceBody] = await Promise.all([
          trackingResponse.json() as Promise<unknown>,
          clearanceResponse.json() as Promise<unknown>,
        ]);
        const parsedTracking =
          parseMaintenanceSlaIncidentTracking(trackingBody);
        const parsedClearance =
          parseMaintenanceFleetFlightClearance(clearanceBody);
        if (!parsedTracking) {
          throw new Error("정비 작전 현황 응답 형식이 올바르지 않습니다.");
        }
        if (!parsedClearance) {
          throw new Error(
            "함대 비행 준비 상태 응답 형식이 올바르지 않습니다.",
          );
        }

        if (active) {
          setTracking(parsedTracking);
          setFleetClearance(parsedClearance);
          setErrorMessage(null);
        }
      } catch (error) {
        if (active && !controller.signal.aborted) {
          setErrorMessage(
            error instanceof Error
              ? error.message
              : "정비 작전 현황을 불러오지 못했습니다.",
          );
        }
      } finally {
        if (active) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    }

    void loadMissionControl();
    const intervalId = window.setInterval(
      () => void loadMissionControl(),
      AUTO_REFRESH_MS,
    );

    return () => {
      active = false;
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, [refreshKey, refreshRevision]);

  const mission = useMemo(
    () =>
      tracking && fleetClearance
        ? summarizeMission(tracking, fleetClearance)
        : null,
    [fleetClearance, tracking],
  );

  function refresh(): void {
    setRefreshing(true);
    setRefreshRevision((current) => current + 1);
  }

  if (loading && (!tracking || !fleetClearance)) {
    return <MissionControlSkeleton />;
  }

  if (!tracking || !fleetClearance || !mission) {
    return (
      <section
        data-maintenance-mission-control
        role="alert"
        className="mt-6 overflow-hidden rounded-[1.75rem] border border-rose-200 bg-rose-50 p-5 text-sm font-bold text-rose-900 shadow-sm"
      >
        <p className="text-xs font-black uppercase tracking-[0.18em] text-rose-700">
          Maintenance Mission Control
        </p>
        <p className="mt-2">
          {errorMessage ?? "정비 작전 현황을 표시할 수 없습니다."}
        </p>
        <button
          type="button"
          onClick={refresh}
          className="mt-4 rounded-lg bg-rose-900 px-4 py-2 text-xs font-black text-white"
        >
          다시 확인
        </button>
      </section>
    );
  }

  return (
    <section
      data-maintenance-mission-control
      aria-labelledby="maintenance-mission-control-title"
      className="relative mt-6 overflow-hidden rounded-[1.75rem] border border-slate-700 bg-slate-950 text-white shadow-xl shadow-slate-300/40"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_10%_0%,rgba(34,211,238,0.22),transparent_38%),radial-gradient(circle_at_92%_16%,rgba(139,92,246,0.2),transparent_34%)]"
      />

      <div className="relative p-5 sm:p-6 lg:p-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs font-black uppercase tracking-[0.2em] text-cyan-300">
                Maintenance Mission Control
              </p>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-black ${mission.healthStyle}`}
              >
                <span
                  aria-hidden="true"
                  className={`h-1.5 w-1.5 rounded-full ${mission.pulseStyle}`}
                />
                {mission.healthLabel}
              </span>
            </div>
            <h2
              id="maintenance-mission-control-title"
              className="mt-2 text-2xl font-black tracking-tight sm:text-3xl"
            >
              정비 작전 현황 보드
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
              작업 접수부터 SLA 대응과 최종 비행 판정까지 현재 흐름을
              한눈에 확인합니다.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <p
              aria-live="polite"
              className="rounded-lg border border-slate-700 bg-slate-900/70 px-3 py-2 text-xs text-slate-300"
            >
              {formatKoreanDateTime(tracking.evaluatedAt)} · 30초 자동 갱신
            </p>
            <button
              type="button"
              onClick={refresh}
              disabled={refreshing}
              className="rounded-lg border border-cyan-300/40 bg-cyan-300/10 px-3 py-2 text-xs font-black text-cyan-100 transition hover:bg-cyan-300/20 disabled:cursor-wait disabled:opacity-60"
            >
              {refreshing ? "갱신 중..." : "지금 갱신"}
            </button>
          </div>
        </div>

        {errorMessage && (
          <p className="mt-4 rounded-xl border border-amber-300/30 bg-amber-300/10 px-4 py-3 text-xs font-bold text-amber-100">
            최신 값 갱신 실패 · 이전 현황을 표시합니다: {errorMessage}
          </p>
        )}

        <div className="mt-6 grid gap-5 xl:grid-cols-[minmax(0,1.65fr)_minmax(19rem,0.75fr)]">
          <div className="rounded-2xl border border-slate-700/80 bg-slate-900/65 p-4 sm:p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-black text-white">
                  작전 단계 현황
                </h3>
                <p className="mt-1 text-xs text-slate-400">
                  전체 작업 {tracking.totalWorkOrders}건 기준
                </p>
              </div>
              <span className="rounded-full bg-slate-800 px-3 py-1 text-xs font-black text-slate-200">
                대응 필요 {mission.attentionCount}건
              </span>
            </div>

            <ol className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {mission.stages.map((stage, index) => (
                <li
                  key={stage.key}
                  className="relative rounded-xl border border-slate-700 bg-slate-950/70 p-4"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span
                      aria-hidden="true"
                      className={`h-2.5 w-2.5 rounded-full ${stage.accent}`}
                    />
                    <span className="text-[10px] font-black tracking-[0.16em] text-slate-500">
                      0{index + 1}
                    </span>
                  </div>
                  <p className="mt-4 text-2xl font-black">{stage.count}</p>
                  <p className="mt-1 text-sm font-black text-slate-100">
                    {stage.label}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {stage.description}
                  </p>
                </li>
              ))}
            </ol>
          </div>

          <div className="rounded-2xl border border-slate-700/80 bg-slate-900/65 p-4 sm:p-5">
            <h3 className="text-sm font-black text-white">비행 준비 상태</h3>
            <p className="mt-1 text-xs text-slate-400">
              전체 함대의 최신 비행 허가 판정 · 총{" "}
              {fleetClearance.totalDrones}대
            </p>
            <div className="mt-5 flex items-center gap-5">
              <div
                role="img"
                aria-label={`비행 가능 ${mission.clearance.cleared}대, 점검 대기 ${mission.clearance.pending}대, 운항 중지 ${mission.clearance.grounded}대`}
                className="grid h-28 w-28 shrink-0 place-items-center rounded-full"
                style={{ background: mission.clearance.gradient }}
              >
                <div className="grid h-20 w-20 place-items-center rounded-full bg-slate-950 text-center">
                  <div>
                    <p className="text-2xl font-black">
                      {mission.clearance.cleared}
                    </p>
                    <p className="text-[10px] font-bold text-slate-400">
                      비행 가능
                    </p>
                  </div>
                </div>
              </div>
              <dl className="min-w-0 flex-1 space-y-3 text-xs">
                <ClearanceLegend
                  color="bg-emerald-400"
                  label="비행 가능"
                  value={mission.clearance.cleared}
                />
                <ClearanceLegend
                  color="bg-amber-400"
                  label="점검 대기"
                  value={mission.clearance.pending}
                />
                <ClearanceLegend
                  color="bg-rose-400"
                  label="운항 중지"
                  value={mission.clearance.grounded}
                />
              </dl>
            </div>
          </div>
        </div>

        <div className="mt-5 rounded-2xl border border-slate-700/80 bg-slate-900/65 p-4 sm:p-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h3 className="text-sm font-black text-white">긴급 작업 큐</h3>
              <p className="mt-1 text-xs text-slate-400">
                SLA·Incident·마감 정합성 기준 상위 3건
              </p>
            </div>
            <Link
              href="/maintenance?status=OPEN"
              className="text-xs font-black text-cyan-300 transition hover:text-cyan-200"
            >
              점검 대기 전체 보기 →
            </Link>
          </div>

          {mission.urgentItems.length === 0 ? (
            <p className="mt-4 rounded-xl border border-emerald-300/20 bg-emerald-300/10 px-4 py-4 text-sm font-bold text-emerald-100">
              즉시 대응이 필요한 SLA 또는 마감 정합성 경고가 없습니다.
            </p>
          ) : (
            <div className="mt-4 grid gap-3 lg:grid-cols-3">
              {mission.urgentItems.map((item, index) => (
                <article
                  key={item.workOrderId}
                  className="group rounded-xl border border-slate-700 bg-slate-950/75 p-4 transition hover:border-cyan-400/60"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">
                        Priority 0{index + 1}
                      </p>
                      <h4 className="mt-1 text-base font-black text-white">
                        Drone #{item.droneId}
                      </h4>
                      <p className="mt-0.5 text-xs text-slate-400">
                        작업 #{item.workOrderId} · Incident #{item.incidentId}
                      </p>
                    </div>
                    <span
                      className={`rounded-full border px-2.5 py-1 text-[10px] font-black ${slaStyles[item.slaStatus]}`}
                    >
                      {slaLabels[item.slaStatus]}
                    </span>
                  </div>
                  <p className="mt-4 text-sm font-black text-slate-100">
                    {formatUrgency(item)}
                  </p>
                  <p className="mt-1 line-clamp-2 min-h-10 text-xs leading-5 text-slate-400">
                    {item.recommendedAction}
                  </p>
                  <Link
                    href={`/maintenance?droneId=${item.droneId}&workOrderId=${item.workOrderId}#maintenance-work-order-${item.workOrderId}`}
                    className="mt-4 inline-flex rounded-lg bg-cyan-400 px-3 py-2 text-xs font-black text-slate-950 transition group-hover:bg-cyan-300"
                  >
                    작업 열기
                  </Link>
                </article>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function summarizeMission(
  tracking: MaintenanceSlaIncidentTracking,
  fleetClearance: MaintenanceFleetFlightClearance,
) {
  const responseStatuses = new Set([
    "ESCALATION_PENDING",
    "ASSIGNMENT_REQUIRED",
    "IN_RESPONSE",
  ]);
  const stages: MissionStage[] = stageDefinitions.map((stage) => ({
    ...stage,
    count:
      stage.key === "SLA_RESPONSE"
        ? tracking.items.filter((item) =>
            responseStatuses.has(item.responseStatus),
          ).length
        : stage.key === "DECIDED"
          ? tracking.items.filter(
              (item) =>
                item.workOrderStatus === "COMPLETED" ||
                item.workOrderStatus === "GROUNDED",
            ).length
          : tracking.items.filter(
              (item) => item.workOrderStatus === stage.key,
            ).length,
  }));

  const cleared = fleetClearance.clearances.filter(
    (clearance) =>
      clearance.flightAllowed && !clearance.attentionRequired,
  ).length;
  const pending = fleetClearance.clearances.filter(
    (clearance) =>
      clearance.flightAllowed && clearance.attentionRequired,
  ).length;
  const grounded = fleetClearance.clearances.filter(
    (clearance) => !clearance.flightAllowed,
  ).length;
  const total = Math.max(cleared + pending + grounded, 1);
  const clearedEnd = (cleared / total) * 100;
  const pendingEnd = clearedEnd + (pending / total) * 100;
  const gradient =
    cleared + pending + grounded === 0
      ? "conic-gradient(#475569 0 100%)"
      : `conic-gradient(#34d399 0 ${clearedEnd}%, #fbbf24 ${clearedEnd}% ${pendingEnd}%, #fb7185 ${pendingEnd}% 100%)`;

  const urgentItems = [...tracking.items]
    .filter(
      (item) =>
        item.slaStatus === "OVERDUE" ||
        item.slaStatus === "DUE_SOON" ||
        item.closureStatus === "REVIEW_REQUIRED" ||
        item.responseStatus === "ASSIGNMENT_REQUIRED" ||
        item.responseStatus === "ESCALATION_PENDING",
    )
    .sort(compareUrgency)
    .slice(0, 3);

  const attentionCount = tracking.items.filter(
    (item) =>
      item.slaStatus === "OVERDUE" ||
      item.slaStatus === "DUE_SOON" ||
      item.closureStatus === "REVIEW_REQUIRED",
  ).length;
  const hasCritical =
    tracking.overdueWorkOrders > 0 ||
    tracking.closureConsistencyAlerts > 0 ||
    fleetClearance.blockedDrones > 0;
  const hasWarning =
    attentionCount > 0 || fleetClearance.attentionDrones > 0;

  return {
    stages,
    urgentItems,
    attentionCount,
    clearance: { cleared, pending, grounded, gradient },
    healthLabel: hasCritical
      ? "즉시 대응 필요"
      : hasWarning
        ? "주의 관제"
        : "운영 안정",
    healthStyle: hasCritical
      ? "border-rose-300/50 bg-rose-400/15 text-rose-100"
      : hasWarning
        ? "border-amber-300/50 bg-amber-400/15 text-amber-100"
        : "border-emerald-300/50 bg-emerald-400/15 text-emerald-100",
    pulseStyle: hasCritical
      ? "bg-rose-300 animate-pulse"
      : hasWarning
        ? "bg-amber-300"
        : "bg-emerald-300",
  };
}

function compareUrgency(
  left: MaintenanceSlaIncidentTrackingItem,
  right: MaintenanceSlaIncidentTrackingItem,
): number {
  const slaRank = {
    OVERDUE: 0,
    DUE_SOON: 1,
    ON_TRACK: 2,
    NOT_APPLICABLE: 3,
  } as const;
  const rankDifference = slaRank[left.slaStatus] - slaRank[right.slaStatus];
  if (rankDifference !== 0) return rankDifference;

  const overdueDifference =
    (right.slaOverdueMinutes ?? -1) - (left.slaOverdueMinutes ?? -1);
  if (overdueDifference !== 0) return overdueDifference;

  const leftDueAt = left.slaDueAt ? Date.parse(left.slaDueAt) : Infinity;
  const rightDueAt = right.slaDueAt ? Date.parse(right.slaDueAt) : Infinity;
  return leftDueAt - rightDueAt || left.workOrderId - right.workOrderId;
}

function formatUrgency(item: MaintenanceSlaIncidentTrackingItem): string {
  if (item.slaStatus === "OVERDUE") {
    return `${formatMinutes(item.slaOverdueMinutes ?? 0)} 초과`;
  }
  if (item.slaStatus === "DUE_SOON" && item.slaDueAt) {
    return `${formatKoreanDateTime(item.slaDueAt)} 마감`;
  }
  if (item.closureStatus === "REVIEW_REQUIRED") {
    return "마감 상태 수동 점검 필요";
  }
  return "운영자 대응 필요";
}

function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes}분`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder === 0 ? `${hours}시간` : `${hours}시간 ${remainder}분`;
}

function ClearanceLegend({
  color,
  label,
  value,
}: {
  color: string;
  label: string;
  value: number;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="flex items-center gap-2 text-slate-300">
        <span aria-hidden="true" className={`h-2 w-2 rounded-full ${color}`} />
        {label}
      </dt>
      <dd className="font-black text-white">{value}대</dd>
    </div>
  );
}

function MissionControlSkeleton() {
  return (
    <section
      data-maintenance-mission-control
      aria-busy="true"
      aria-label="정비 작전 현황을 불러오는 중"
      className="mt-6 overflow-hidden rounded-[1.75rem] border border-slate-700 bg-slate-950 p-6 text-white shadow-xl"
    >
      <div className="animate-pulse">
        <div className="h-3 w-48 rounded bg-slate-700" />
        <div className="mt-4 h-8 w-72 max-w-full rounded bg-slate-800" />
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((item) => (
            <div key={item} className="h-28 rounded-xl bg-slate-800" />
          ))}
        </div>
      </div>
    </section>
  );
}
