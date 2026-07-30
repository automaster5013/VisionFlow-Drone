"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  MaintenanceSlaIncidentTrackingPanel,
} from "@/components/maintenance/maintenance-sla-incident-tracking-panel";
import { formatKoreanDateTime } from "@/lib/date";
import {
  parseMaintenancePriorityQueue,
  type MaintenancePriorityItem,
  type MaintenancePriorityLevel,
  type MaintenancePriorityQueue,
  type MaintenanceSlaStatus,
} from "@/types/maintenance-priority";
import {
  parseMaintenanceSlaAutomationStatus,
  type MaintenanceSlaAutomationStatus,
} from "@/types/maintenance-sla-automation";

const priorityLabels: Record<MaintenancePriorityLevel, string> = {
  CRITICAL: "긴급",
  HIGH: "높음",
  MEDIUM: "주의",
  LOW: "정상",
};

const priorityStyles: Record<MaintenancePriorityLevel, string> = {
  CRITICAL: "border-rose-300 bg-rose-50 text-rose-900",
  HIGH: "border-orange-300 bg-orange-50 text-orange-900",
  MEDIUM: "border-amber-300 bg-amber-50 text-amber-900",
  LOW: "border-emerald-300 bg-emerald-50 text-emerald-900",
};

const slaStyles: Record<MaintenanceSlaStatus, string> = {
  OVERDUE: "bg-rose-100 text-rose-900",
  DUE_SOON: "bg-amber-100 text-amber-900",
  ON_TRACK: "bg-sky-100 text-sky-900",
  NOT_APPLICABLE: "bg-slate-100 text-slate-600",
};

interface MaintenancePriorityPanelProps {
  refreshKey: number;
}

export function MaintenancePriorityPanel({
  refreshKey,
}: MaintenancePriorityPanelProps) {
  const [queue, setQueue] = useState<MaintenancePriorityQueue | null>(null);
  const [slaAutomation, setSlaAutomation] =
    useState<MaintenanceSlaAutomationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    fetch("/api/maintenance/priorities", {
      headers: { Accept: "application/json" },
      cache: "no-store",
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(
            `정비 우선조치 큐 조회 실패: HTTP ${response.status}`,
          );
        }
        return response.json() as Promise<unknown>;
      })
      .then((body) => {
        const parsed = parseMaintenancePriorityQueue(body);
        if (!parsed) {
          throw new Error(
            "정비 우선조치 큐 응답 형식이 올바르지 않습니다.",
          );
        }
        if (active) {
          setQueue(parsed);
          setErrorMessage(null);
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setErrorMessage(
            error instanceof Error
              ? error.message
              : "정비 우선조치 큐를 불러오지 못했습니다.",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [refreshKey]);

  useEffect(() => {
    let active = true;

    fetch("/api/maintenance/sla", {
      headers: { Accept: "application/json" },
      cache: "no-store",
    })
      .then(async (response) => {
        if (!response.ok) return null;
        return response.json() as Promise<unknown>;
      })
      .then((body) => {
        if (!active || body === null) return;
        setSlaAutomation(
          parseMaintenanceSlaAutomationStatus(body),
        );
      })
      .catch(() => {
        if (active) setSlaAutomation(null);
      });

    return () => {
      active = false;
    };
  }, [refreshKey]);

  if (loading && !queue) {
    return (
      <>
        <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600 shadow-sm">
          <p>드론별 정비 우선순위를 계산하고 있습니다.</p>
          <p
            data-maintenance-sla-automation
            className="mt-1 text-xs"
          >
            SLA 자동 Incident 상향 상태를 확인하고 있습니다.
          </p>
        </section>
        <MaintenanceSlaIncidentTrackingPanel refreshKey={refreshKey} />
      </>
    );
  }

  if (!queue) {
    return (
      <>
        <section
          role="alert"
          className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-5 text-sm font-bold text-red-900"
        >
          {errorMessage ?? "정비 우선조치 큐를 표시할 수 없습니다."}
        </section>
        <MaintenanceSlaIncidentTrackingPanel refreshKey={refreshKey} />
      </>
    );
  }

  return (
    <>
      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.16em] text-orange-700">
              Maintenance Priority Queue
            </p>
            <h2 className="mt-1 text-xl font-black text-slate-950">
              정비 우선조치 큐
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              운영 규칙 기반 평가 ·{" "}
              {formatKoreanDateTime(queue.evaluatedAt)}
            </p>
            <div
              data-maintenance-sla-automation
              className="mt-2 inline-flex flex-wrap items-center gap-2 rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-700"
            >
              <span className="font-black">SLA 자동 Incident 상향</span>
              <span
                className={
                  slaAutomation?.automationEnabled
                    ? "font-black text-emerald-700"
                    : "font-black text-slate-500"
                }
              >
                {slaAutomation === null
                  ? "확인 중"
                  : slaAutomation.automationEnabled
                    ? "ON"
                    : "OFF"}
              </span>
              {slaAutomation && (
                <span>
                  OPEN {slaAutomation.openSlaMinutes}분 · 진행{" "}
                  {slaAutomation.inProgressSlaMinutes}분 ·{" "}
                  {Math.round(slaAutomation.scanDelayMs / 1000)}초 간격
                </span>
              )}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 text-center text-xs sm:grid-cols-5">
            <QueueCounter
              label="긴급·높음"
              value={queue.urgentDrones}
              style="bg-rose-50 text-rose-900"
            />
            <QueueCounter
              label="주의"
              value={queue.attentionDrones}
              style="bg-amber-50 text-amber-900"
            />
            <QueueCounter
              label="SLA 초과"
              value={queue.overdueDrones}
              style="bg-rose-100 text-rose-950"
            />
            <QueueCounter
              label="SLA 임박"
              value={queue.dueSoonDrones}
              style="bg-amber-100 text-amber-950"
            />
            <QueueCounter
              label="정상"
              value={queue.normalDrones}
              style="bg-emerald-50 text-emerald-900"
            />
          </div>
        </div>

        {errorMessage && (
          <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs font-bold text-amber-900">
            최신 값 갱신 실패: {errorMessage}
          </p>
        )}

        <div className="mt-5 space-y-3">
          {queue.priorities.map((item) => (
            <PriorityRow key={item.droneId} item={item} />
          ))}
        </div>
      </section>
      <MaintenanceSlaIncidentTrackingPanel refreshKey={refreshKey} />
    </>
  );
}

function PriorityRow({ item }: { item: MaintenancePriorityItem }) {
  const link = item.workOrderId === null
    ? `/drones?droneId=${item.droneId}`
    : `/maintenance?droneId=${item.droneId}` +
      `&workOrderId=${item.workOrderId}`;

  return (
    <article className="grid gap-3 rounded-xl border border-slate-200 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto] lg:items-center">
      <div className="flex items-center gap-3">
        <span
          className={`rounded-full border px-2.5 py-1 text-xs font-black ${priorityStyles[item.priority]}`}
        >
          {priorityLabels[item.priority]}
        </span>
        <div>
          <p className="font-black text-slate-950">
            Drone #{item.droneId}
          </p>
          <p className="text-xs font-bold text-slate-500">
            위험도 {item.riskScore}/100
            {item.waitingMinutes === null
              ? ""
              : ` · 대기 ${formatWaiting(item.waitingMinutes)}`}
          </p>
          <span
            className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-[11px] font-black ${slaStyles[item.slaStatus]}`}
            title={
              item.slaDueAt === null
                ? undefined
                : `SLA 기한 ${formatKoreanDateTime(item.slaDueAt)}`
            }
          >
            {formatSla(item)}
          </span>
        </div>
      </div>
      <div>
        <p className="text-sm font-bold text-slate-800">
          {item.recommendedAction}
        </p>
        <p className="mt-1 text-xs text-slate-500">{item.reason}</p>
      </div>
      <Link
        href={link}
        className="justify-self-start rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-bold text-slate-700 lg:justify-self-end"
      >
        {item.workOrderId === null ? "관제 확인" : "작업 열기"}
      </Link>
    </article>
  );
}

function QueueCounter({
  label,
  value,
  style,
}: {
  label: string;
  value: number;
  style: string;
}) {
  return (
    <div className={`rounded-lg px-3 py-2 ${style}`}>
      <p className="font-bold">{label}</p>
      <p className="mt-0.5 text-lg font-black">{value}대</p>
    </div>
  );
}

function formatWaiting(minutes: number): string {
  if (minutes < 60) return `${minutes}분`;
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)}시간`;
  return `${Math.floor(minutes / (24 * 60))}일`;
}

function formatSla(item: MaintenancePriorityItem): string {
  if (
    item.slaStatus === "OVERDUE" &&
    item.slaOverdueMinutes !== null
  ) {
    return `SLA ${formatWaiting(item.slaOverdueMinutes)} 초과`;
  }
  if (
    item.slaStatus === "DUE_SOON" &&
    item.slaRemainingMinutes !== null
  ) {
    return `SLA ${formatWaiting(item.slaRemainingMinutes)} 남음`;
  }
  if (
    item.slaStatus === "ON_TRACK" &&
    item.slaRemainingMinutes !== null
  ) {
    return `SLA ${formatWaiting(item.slaRemainingMinutes)} 남음`;
  }
  return "SLA 종료";
}
