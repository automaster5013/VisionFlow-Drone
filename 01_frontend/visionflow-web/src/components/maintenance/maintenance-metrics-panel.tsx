"use client";

import { useEffect, useMemo, useState } from "react";

import { formatKoreanDateTime } from "@/lib/date";
import {
  parseMaintenanceMetrics,
  type MaintenanceMetrics,
} from "@/types/maintenance-metrics";

const windows = [7, 30, 90] as const;

const modeLabels = {
  OFF: "게이트 꺼짐",
  ADVISORY: "주의 모드",
  ENFORCED: "강제 차단",
} as const;

interface MaintenanceMetricsPanelProps {
  refreshKey: number;
}

export function MaintenanceMetricsPanel({
  refreshKey,
}: MaintenanceMetricsPanelProps) {
  const [windowDays, setWindowDays] = useState<number>(30);
  const [metrics, setMetrics] = useState<MaintenanceMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    fetch(`/api/maintenance/metrics?windowDays=${windowDays}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`정비 KPI 조회 실패: HTTP ${response.status}`);
        }
        return response.json() as Promise<unknown>;
      })
      .then((body) => {
        const parsed = parseMaintenanceMetrics(body);
        if (!parsed) {
          throw new Error("정비 KPI 응답 형식이 올바르지 않습니다.");
        }
        if (active) {
          setMetrics(parsed);
          setErrorMessage(null);
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setErrorMessage(
            error instanceof Error
              ? error.message
              : "정비 KPI를 불러오지 못했습니다.",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [refreshKey, windowDays]);

  const statusRows = useMemo(
    () =>
      metrics
        ? [
            {
              label: "점검 대기",
              value: metrics.openWorkOrders,
              color: "bg-amber-500",
            },
            {
              label: "점검 중",
              value: metrics.inProgressWorkOrders,
              color: "bg-sky-500",
            },
            {
              label: "재운항 승인",
              value: metrics.completedWorkOrders,
              color: "bg-emerald-500",
            },
            {
              label: "운항 중지",
              value: metrics.groundedWorkOrders,
              color: "bg-rose-500",
            },
          ]
        : [],
    [metrics],
  );
  const maximumStatus = Math.max(
    1,
    ...statusRows.map((row) => row.value),
  );

  if (loading && !metrics) {
    return (
      <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600 shadow-sm">
        정비 운영 KPI를 집계하고 있습니다.
      </section>
    );
  }

  if (!metrics) {
    return (
      <section
        role="alert"
        className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-5 text-sm font-bold text-red-900"
      >
        {errorMessage ?? "정비 운영 KPI를 표시할 수 없습니다."}
      </section>
    );
  }

  return (
    <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.16em] text-cyan-700">
            Maintenance KPI
          </p>
          <h2 className="mt-1 text-xl font-black text-slate-950">
            정비 운영 현황
          </h2>
          <p className="mt-1 text-xs text-slate-500">
            마지막 집계 {formatKoreanDateTime(metrics.generatedAt)}
          </p>
        </div>
        <div
          className="flex rounded-xl border border-slate-200 bg-slate-50 p-1"
          aria-label="정비 KPI 조회 기간"
        >
          {windows.map((days) => (
            <button
              key={days}
              type="button"
              onClick={() => {
                if (windowDays === days) return;
                setLoading(true);
                setWindowDays(days);
              }}
              aria-pressed={windowDays === days}
              className={`rounded-lg px-3 py-1.5 text-xs font-black ${
                windowDays === days
                  ? "bg-slate-950 text-white"
                  : "text-slate-600"
              }`}
            >
              {days}일
            </button>
          ))}
        </div>
      </div>

      {errorMessage && (
        <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs font-bold text-amber-900">
          최신 값 갱신 실패: {errorMessage}
        </p>
      )}

      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label={`${metrics.windowDays}일 작업`}
          value={`${metrics.totalWorkOrders}건`}
          detail={`처리 ${metrics.resolvedWorkOrders}건`}
        />
        <MetricCard
          label="처리 완료율"
          value={`${metrics.resolutionRatePercent.toFixed(1)}%`}
          detail="재운항 승인·운항 중지 포함"
        />
        <MetricCard
          label="평균 점검 착수"
          value={formatDuration(metrics.averageStartDelayMinutes)}
          detail="접수부터 점검 시작까지"
        />
        <MetricCard
          label="평균 처리시간"
          value={formatDuration(metrics.averageResolutionMinutes)}
          detail="접수부터 최종 판정까지"
        />
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-200 p-4">
          <h3 className="font-black text-slate-900">작업 상태 분포</h3>
          <div className="mt-4 space-y-3">
            {statusRows.map((row) => (
              <div key={row.label}>
                <div className="mb-1 flex items-center justify-between text-xs font-bold text-slate-600">
                  <span>{row.label}</span>
                  <span>{row.value}건</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full ${row.color}`}
                    style={{
                      width: `${row.value === 0
                        ? 0
                        : Math.max(
                            8,
                            (row.value / maximumStatus) * 100,
                          )}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-black text-slate-900">
              현재 함대 비행 게이트
            </h3>
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-black ${
                metrics.gateEnforced
                  ? "bg-rose-100 text-rose-800"
                  : "bg-cyan-100 text-cyan-800"
              }`}
            >
              {modeLabels[metrics.gateMode]}
            </span>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <FleetMetric label="전체" value={metrics.totalDrones} />
            <FleetMetric label="비행 가능" value={metrics.allowedDrones} />
            <FleetMetric label="주의 필요" value={metrics.attentionDrones} />
            <FleetMetric label="비행 차단" value={metrics.blockedDrones} />
          </div>
        </div>
      </div>
    </section>
  );
}

function MetricCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded-xl bg-slate-50 p-4">
      <p className="text-xs font-bold text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-black text-slate-950">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{detail}</p>
    </div>
  );
}

function FleetMetric({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-lg bg-slate-50 p-3">
      <p className="text-xs font-bold text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-black text-slate-950">{value}대</p>
    </div>
  );
}

function formatDuration(minutes: number | null): string {
  if (minutes === null) return "-";
  if (minutes < 60) return `${minutes}분`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder === 0
    ? `${hours}시간`
    : `${hours}시간 ${remainder}분`;
}
