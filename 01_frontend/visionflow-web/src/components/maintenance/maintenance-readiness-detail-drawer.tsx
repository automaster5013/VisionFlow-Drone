"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

import { formatKoreanDateTime } from "@/lib/date";
import type {
  MaintenanceFlightClearance,
  MaintenanceFlightGateMode,
} from "@/types/maintenance-flight-clearance";
import type { MaintenanceSlaIncidentTrackingItem } from "@/types/maintenance-sla-incident-tracking";

export type MaintenanceReadinessCategory =
  | "CLEARED"
  | "ATTENTION"
  | "BLOCKED";

export type MaintenanceReadinessFreshnessStatus =
  | "FRESH"
  | "DELAYED"
  | "STALE";

interface MaintenanceReadinessDetailDrawerProps {
  clearance: MaintenanceFlightClearance;
  category: MaintenanceReadinessCategory;
  trackingItem: MaintenanceSlaIncidentTrackingItem | null;
  mode: MaintenanceFlightGateMode;
  enforced: boolean;
  trackingEvaluatedAt: string;
  clearanceEvaluatedAt: string;
  trackingFreshness: MaintenanceReadinessFreshnessStatus;
  clearanceFreshness: MaintenanceReadinessFreshnessStatus;
  returnFocusElement: HTMLButtonElement | null;
  onClose: () => void;
}

const readinessDefinitions = {
  CLEARED: {
    label: "비행 가능",
    badge: "border-emerald-300/40 bg-emerald-400/15 text-emerald-100",
  },
  ATTENTION: {
    label: "점검 대기",
    badge: "border-amber-300/40 bg-amber-400/15 text-amber-100",
  },
  BLOCKED: {
    label: "운항 중지",
    badge: "border-rose-300/40 bg-rose-400/15 text-rose-100",
  },
} as const;

const freshnessDefinitions = {
  FRESH: {
    label: "최신",
    badge: "border-emerald-300/40 bg-emerald-400/15 text-emerald-100",
  },
  DELAYED: {
    label: "지연",
    badge: "border-amber-300/40 bg-amber-400/15 text-amber-100",
  },
  STALE: {
    label: "오래됨",
    badge: "border-rose-300/40 bg-rose-400/15 text-rose-100",
  },
} as const;

const workOrderStatusLabels = {
  OPEN: "점검 대기",
  IN_PROGRESS: "점검 중",
  COMPLETED: "재운항 승인",
  GROUNDED: "운항 중지",
} as const;

const clearanceStatusLabels = {
  PENDING_INSPECTION: "점검 판정 대기",
  CLEARED: "비행 허가",
  GROUNDED: "비행 차단",
} as const;

const incidentStatusLabels = {
  OPEN: "상황 대기",
  IN_PROGRESS: "대응 중",
  RESOLVED: "조치 완료",
  CLOSED: "종결",
} as const;

const priorityLabels = {
  LOW: "낮음",
  MEDIUM: "보통",
  HIGH: "높음",
  CRITICAL: "긴급",
} as const;

const responseStatusLabels = {
  MONITORING: "감시 중",
  ESCALATION_PENDING: "상향 대기",
  ASSIGNMENT_REQUIRED: "담당자 필요",
  IN_RESPONSE: "대응 중",
  COMPLETED: "대응 완료",
} as const;

const closureStatusLabels = {
  RESPONSE_ACTIVE: "Incident 대응 중",
  WORK_ORDER_PENDING: "정비 마감 필요",
  RETURN_TO_SERVICE_CONFIRMED: "재운항 확인",
  GROUNDED_CONFIRMED: "운항 중지 확인",
  REVIEW_REQUIRED: "수동 검토 필요",
} as const;

const gateModeLabels = {
  OFF: "비활성",
  ADVISORY: "주의 모드",
  ENFORCED: "강제 차단",
} as const;

export function MaintenanceReadinessDetailDrawer({
  clearance,
  category,
  trackingItem,
  mode,
  enforced,
  trackingEvaluatedAt,
  clearanceEvaluatedAt,
  trackingFreshness,
  clearanceFreshness,
  returnFocusElement,
  onClose,
}: MaintenanceReadinessDetailDrawerProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  const readiness = readinessDefinitions[category];

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
      if (event.key === "Tab") {
        const focusableElements = drawerRef.current?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
        if (!focusableElements || focusableElements.length === 0) return;
        const first = focusableElements[0];
        const last = focusableElements[focusableElements.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      returnFocusElement?.focus();
    };
  }, [onClose, returnFocusElement]);

  return (
    <div
      data-maintenance-readiness-drawer
      className="fixed inset-0 z-50 flex justify-end"
    >
      <button
        type="button"
        aria-label="기체 관제 상세 닫기"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-slate-950/75 backdrop-blur-sm"
      />
      <aside
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="maintenance-readiness-drawer-title"
        className="relative h-full w-full max-w-xl overflow-y-auto border-l border-slate-700 bg-slate-950 text-white shadow-2xl shadow-black/60"
      >
        <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/95 px-5 py-4 backdrop-blur sm:px-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[11px] font-black uppercase tracking-[0.18em] text-cyan-300">
                Fleet Readiness Detail
              </p>
              <h3
                id="maintenance-readiness-drawer-title"
                className="mt-1 text-2xl font-black"
              >
                Drone #{clearance.droneId} 관제 상세
              </h3>
            </div>
            <button
              ref={closeButtonRef}
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-600 px-3 py-2 text-xs font-black text-slate-200 transition hover:border-cyan-300 hover:text-cyan-100 focus:outline-none focus:ring-2 focus:ring-cyan-300"
            >
              닫기
            </button>
          </div>
        </header>

        <div className="space-y-5 p-5 sm:p-6">
          <section className="rounded-2xl border border-slate-700 bg-slate-900/70 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs font-black text-slate-400">현재 판정</p>
                <p className="mt-2 text-xl font-black text-white">
                  {readiness.label}
                </p>
              </div>
              <span
                className={`rounded-full border px-3 py-1.5 text-xs font-black ${readiness.badge}`}
              >
                {readiness.label}
              </span>
            </div>
            <p className="mt-4 rounded-xl border border-slate-700 bg-slate-950/80 px-4 py-3 text-sm leading-6 text-slate-200">
              {clearance.reason}
            </p>
            <dl className="mt-4 grid gap-3 sm:grid-cols-2">
              <DetailValue
                label="비행 게이트"
                value={`${gateModeLabels[mode]} · ${enforced ? "적용" : "미적용"}`}
              />
              <DetailValue
                label="비행 허가"
                value={clearance.flightAllowed ? "허용" : "차단"}
              />
              <DetailValue
                label="정비 상태"
                value={
                  clearance.workOrderStatus
                    ? workOrderStatusLabels[clearance.workOrderStatus]
                    : "연결 작업 없음"
                }
              />
              <DetailValue
                label="운항 판정"
                value={
                  clearance.clearanceStatus
                    ? clearanceStatusLabels[clearance.clearanceStatus]
                    : "정상 운항"
                }
              />
            </dl>
          </section>

          <section className="rounded-2xl border border-slate-700 bg-slate-900/70 p-5">
            <h4 className="text-sm font-black text-white">데이터 신선도</h4>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <FreshnessValue
                label="SLA Incident 판정"
                status={trackingFreshness}
                evaluatedAt={trackingEvaluatedAt}
              />
              <FreshnessValue
                label="함대 비행 판정"
                status={clearanceFreshness}
                evaluatedAt={clearanceEvaluatedAt}
              />
            </div>
          </section>

          <section className="rounded-2xl border border-slate-700 bg-slate-900/70 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h4 className="text-sm font-black text-white">
                  작업지시·Incident
                </h4>
                <p className="mt-1 text-xs text-slate-400">
                  현재 비행 판정에 연결된 운영 대응 상태
                </p>
              </div>
              {clearance.workOrderId !== null && (
                <span className="rounded-full bg-slate-800 px-3 py-1 text-[11px] font-black text-slate-200">
                  작업 #{clearance.workOrderId}
                </span>
              )}
            </div>

            {trackingItem ? (
              <>
                <dl className="mt-4 grid gap-3 sm:grid-cols-2">
                  <DetailValue
                    label="Incident"
                    value={`#${trackingItem.incidentId} · ${
                      trackingItem.incidentStatus
                        ? incidentStatusLabels[trackingItem.incidentStatus]
                        : "연결 확인 필요"
                    }`}
                  />
                  <DetailValue
                    label="우선순위"
                    value={
                      trackingItem.incidentPriority
                        ? priorityLabels[trackingItem.incidentPriority]
                        : "미지정"
                    }
                  />
                  <DetailValue
                    label="담당자"
                    value={trackingItem.incidentAssignee ?? "배정 대기"}
                  />
                  <DetailValue
                    label="SLA"
                    value={formatSlaState(trackingItem)}
                  />
                  <DetailValue
                    label="대응 상태"
                    value={responseStatusLabels[trackingItem.responseStatus]}
                  />
                  <DetailValue
                    label="마감 정합성"
                    value={closureStatusLabels[trackingItem.closureStatus]}
                  />
                </dl>
                {trackingItem.incidentTitle && (
                  <p className="mt-4 text-sm font-black text-slate-100">
                    {trackingItem.incidentTitle}
                  </p>
                )}
                <ActionSummary
                  label="권장 대응"
                  value={trackingItem.recommendedAction}
                />
                <ActionSummary
                  label="마감 권고"
                  value={trackingItem.closureRecommendedAction}
                />
              </>
            ) : (
              <p className="mt-4 rounded-xl border border-emerald-300/20 bg-emerald-300/10 px-4 py-4 text-sm font-bold text-emerald-100">
                현재 비행 판정에 연결된 미해결 정비 작업이 없습니다.
              </p>
            )}
          </section>

          <nav
            aria-label={`Drone ${clearance.droneId} 관제 상세 이동`}
            className="grid gap-2 sm:grid-cols-2"
          >
            <Link
              href={`/drones/${clearance.droneId}`}
              className="rounded-xl border border-slate-600 px-4 py-3 text-center text-sm font-black text-slate-100 transition hover:border-cyan-300 hover:text-cyan-100"
            >
              기체 상세 보기
            </Link>
            {clearance.workOrderId !== null && (
              <Link
                href={`/maintenance?droneId=${clearance.droneId}&workOrderId=${clearance.workOrderId}#maintenance-work-order-${clearance.workOrderId}`}
                className="rounded-xl bg-cyan-400 px-4 py-3 text-center text-sm font-black text-slate-950 transition hover:bg-cyan-300"
              >
                작업지시 열기
              </Link>
            )}
            {trackingItem && (
              <Link
                href={`/incidents/${trackingItem.incidentId}/report`}
                className="rounded-xl border border-violet-300/50 bg-violet-400/10 px-4 py-3 text-center text-sm font-black text-violet-100 transition hover:bg-violet-400/20 sm:col-span-2"
              >
                Incident 보고서 보기
              </Link>
            )}
          </nav>
        </div>
      </aside>
    </div>
  );
}

function DetailValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-950/70 p-3">
      <dt className="text-[11px] font-black text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm font-black text-slate-100">{value}</dd>
    </div>
  );
}

function FreshnessValue({
  label,
  status,
  evaluatedAt,
}: {
  label: string;
  status: MaintenanceReadinessFreshnessStatus;
  evaluatedAt: string;
}) {
  const definition = freshnessDefinitions[status];
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-950/70 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-black text-slate-400">{label}</p>
        <span
          className={`rounded-full border px-2 py-1 text-[10px] font-black ${definition.badge}`}
        >
          {definition.label}
        </span>
      </div>
      <p className="mt-2 text-xs text-slate-300">
        {formatKoreanDateTime(evaluatedAt)}
      </p>
    </div>
  );
}

function ActionSummary({ label, value }: { label: string; value: string }) {
  return (
    <div className="mt-3 rounded-xl border border-slate-700 bg-slate-950/70 px-4 py-3">
      <p className="text-[11px] font-black text-cyan-300">{label}</p>
      <p className="mt-1 text-xs leading-5 text-slate-300">{value}</p>
    </div>
  );
}

function formatSlaState(item: MaintenanceSlaIncidentTrackingItem): string {
  if (item.slaStatus === "OVERDUE") {
    return `${formatMinutes(item.slaOverdueMinutes ?? 0)} 초과`;
  }
  if (item.slaStatus === "DUE_SOON" && item.slaDueAt) {
    return `${formatKoreanDateTime(item.slaDueAt)} 임박`;
  }
  if (item.slaStatus === "ON_TRACK" && item.slaDueAt) {
    return `${formatKoreanDateTime(item.slaDueAt)} 추적`;
  }
  return item.slaStatus === "ON_TRACK" ? "정상 추적" : "적용 제외";
}

function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes}분`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder === 0 ? `${hours}시간` : `${hours}시간 ${remainder}분`;
}
