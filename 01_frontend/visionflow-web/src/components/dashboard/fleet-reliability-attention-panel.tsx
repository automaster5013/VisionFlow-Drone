import Link from "next/link";

import { FleetReliabilityIncidentSyncButton } from "@/components/dashboard/fleet-reliability-incident-sync-button";
import type {
  FleetDroneReliability,
  FleetReliabilityResponse,
  FleetReliabilityStatus,
} from "@/types/fleet-reliability";

interface FleetReliabilityAttentionPanelProps {
  data: FleetReliabilityResponse | null;
  errorMessage: string | null;
}

function statusPresentation(status: FleetReliabilityStatus) {
  return {
    STABLE: {
      label: "안정",
      badge: "bg-emerald-100 text-emerald-800",
      border: "border-emerald-200",
    },
    WATCH: {
      label: "관찰",
      badge: "bg-amber-100 text-amber-900",
      border: "border-amber-200",
    },
    CHECK: {
      label: "점검 필요",
      badge: "bg-rose-100 text-rose-900",
      border: "border-rose-200",
    },
  }[status];
}

function scoreDelta(item: FleetDroneReliability): string {
  if (item.previousScore === null) {
    return "비교할 이전 평가 없음";
  }

  const delta = item.latestScore - item.previousScore;

  return `직전 대비 ${delta > 0 ? "+" : ""}${delta}점`;
}

function reportHref(item: FleetDroneReliability): string {
  return (
    `/drones/${item.droneId}/flight-sessions/` +
    `${encodeURIComponent(item.latestAssessment.sessionId)}/report`
  );
}

export function FleetReliabilityAttentionPanel({
  data,
  errorMessage,
}: FleetReliabilityAttentionPanelProps) {
  const attentionDrones =
    data?.drones.filter((item) => item.status !== "STABLE").slice(0, 4) ?? [];

  return (
    <section
      aria-labelledby="fleet-attention-title"
      className="rounded-2xl border border-cyan-200 bg-white p-5 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.16em] text-cyan-700">
            Flight Quality Watch
          </p>
          <h2
            id="fleet-attention-title"
            className="mt-2 text-xl font-black text-slate-950"
          >
            우선 점검 기체
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            MySQL 품질 평가를 기준으로 점검 필요·관찰 기체를 우선
            표시합니다.
          </p>
        </div>
        <div className="flex flex-wrap items-start justify-end gap-2">
          <FleetReliabilityIncidentSyncButton />
          <Link
            href="/fleet-reliability"
            className="rounded-lg bg-cyan-700 px-4 py-2 text-sm font-bold text-white hover:bg-cyan-600"
          >
            전체 기체 신뢰도
          </Link>
        </div>
      </div>

      {errorMessage ? (
        <div
          role="alert"
          className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900"
        >
          <div className="font-bold">함대 품질 집계를 불러오지 못했습니다.</div>
          <div className="mt-1 break-words text-xs">{errorMessage}</div>
        </div>
      ) : !data ? (
        <div className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">
          함대 품질 집계 결과가 없습니다.
        </div>
      ) : (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <SummaryValue label="평가 기체" value={`${data.droneCount}대`} />
            <SummaryValue
              label="함대 평균"
              value={`${data.fleetAverageScore.toFixed(1)}점`}
            />
            <SummaryValue
              label="확인 필요"
              value={`${data.attentionDroneCount}대`}
            />
          </div>

          {attentionDrones.length > 0 ? (
            <div className="mt-4 grid gap-3 lg:grid-cols-2">
              {attentionDrones.map((item) => (
                <AttentionDroneCard key={item.droneId} item={item} />
              ))}
            </div>
          ) : data.droneCount > 0 ? (
            <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-bold text-emerald-900">
              현재 점검 필요 또는 관찰 상태의 기체가 없습니다.
            </div>
          ) : (
            <div className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">
              저장된 품질 평가가 없습니다. 전체 기체 신뢰도 화면에서 기존
              평가 채우기를 먼저 실행할 수 있습니다.
            </div>
          )}

          <p className="mt-4 text-xs text-slate-500">
            함대 전체 기준이며 대시보드의 세션 필터와는 별도로 집계됩니다.
          </p>
        </>
      )}
    </section>
  );
}

function SummaryValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-slate-50 p-4">
      <div className="text-xs font-bold text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-black text-slate-950">{value}</div>
    </div>
  );
}

function AttentionDroneCard({ item }: { item: FleetDroneReliability }) {
  const presentation = statusPresentation(item.status);

  return (
    <article className={`rounded-xl border bg-slate-50 p-4 ${presentation.border}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-black text-slate-950">
            {item.droneName ?? `Drone #${item.droneId}`}
          </div>
          <div className="mt-1 text-xs text-slate-500">
            {item.droneCode ?? `ID ${item.droneId}`}
          </div>
        </div>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 text-[10px] font-black ${presentation.badge}`}
        >
          {presentation.label}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg bg-white p-3">
          <div className="font-bold text-slate-500">최근 / 평균</div>
          <div className="mt-1 font-black text-slate-950">
            {item.latestScore} / {item.averageScore.toFixed(1)}점
          </div>
        </div>
        <div className="rounded-lg bg-white p-3">
          <div className="font-bold text-slate-500">점수 변화</div>
          <div className="mt-1 font-black text-slate-950">
            {scoreDelta(item)}
          </div>
        </div>
      </div>

      {item.latestAssessment.primaryRisk && (
        <div className="mt-3 rounded-lg bg-white p-3 text-xs">
          <div className="font-black text-slate-900">
            {item.latestAssessment.primaryRisk.title}
          </div>
          <div className="mt-1 line-clamp-2 text-slate-600">
            {item.latestAssessment.primaryRisk.detail}
          </div>
        </div>
      )}

      <div className="mt-3 flex flex-wrap justify-end gap-2">
        <Link
          href={`/drones?droneId=${item.droneId}`}
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-bold text-slate-700"
        >
          드론 관제
        </Link>
        <Link
          href={reportHref(item)}
          className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white"
        >
          최근 진단 보고서
        </Link>
      </div>
    </article>
  );
}
