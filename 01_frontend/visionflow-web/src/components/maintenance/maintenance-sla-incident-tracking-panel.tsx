"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { useOperatorAccess } from "@/components/security/operator-access-provider";
import { formatKoreanDateTime } from "@/lib/date";
import type {
  IncidentPriority,
  IncidentStatus,
} from "@/types/incident";
import {
  parseMaintenanceSlaIncidentTracking,
  type MaintenanceSlaClosureStatus,
  type MaintenanceSlaIncidentTracking,
  type MaintenanceSlaIncidentTrackingItem,
  type MaintenanceSlaResponseStatus,
} from "@/types/maintenance-sla-incident-tracking";
import type {
  FlightClearanceStatus,
  MaintenanceWorkOrderStatus,
} from "@/types/maintenance-work-order";

const priorityLabels: Record<IncidentPriority, string> = {
  LOW: "낮음",
  MEDIUM: "보통",
  HIGH: "높음",
  CRITICAL: "긴급",
};

const statusLabels: Record<IncidentStatus, string> = {
  OPEN: "접수",
  IN_PROGRESS: "처리 중",
  RESOLVED: "해결",
  CLOSED: "종료",
};

const responseLabels: Record<MaintenanceSlaResponseStatus, string> = {
  MONITORING: "감시 중",
  ESCALATION_PENDING: "자동 상향 대기",
  ASSIGNMENT_REQUIRED: "담당자 지정 필요",
  IN_RESPONSE: "대응 중",
  COMPLETED: "조치 종료",
};

const responseStyles: Record<MaintenanceSlaResponseStatus, string> = {
  MONITORING: "bg-sky-100 text-sky-900",
  ESCALATION_PENDING: "bg-rose-100 text-rose-900",
  ASSIGNMENT_REQUIRED: "bg-orange-100 text-orange-900",
  IN_RESPONSE: "bg-violet-100 text-violet-900",
  COMPLETED: "bg-emerald-100 text-emerald-900",
};

const closureLabels: Record<MaintenanceSlaClosureStatus, string> = {
  RESPONSE_ACTIVE: "대응 진행",
  WORK_ORDER_PENDING: "정비 마감 필요",
  RETURN_TO_SERVICE_CONFIRMED: "재운항 확인",
  GROUNDED_CONFIRMED: "운항 중지 확인",
  REVIEW_REQUIRED: "정합성 점검 필요",
};

const closureStyles: Record<MaintenanceSlaClosureStatus, string> = {
  RESPONSE_ACTIVE: "bg-slate-100 text-slate-800",
  WORK_ORDER_PENDING: "bg-amber-100 text-amber-900",
  RETURN_TO_SERVICE_CONFIRMED: "bg-emerald-100 text-emerald-900",
  GROUNDED_CONFIRMED: "bg-rose-100 text-rose-900",
  REVIEW_REQUIRED: "bg-red-100 text-red-900",
};

const workOrderLabels: Record<MaintenanceWorkOrderStatus, string> = {
  OPEN: "점검 대기",
  IN_PROGRESS: "점검 중",
  COMPLETED: "재운항 승인",
  GROUNDED: "운항 중지",
};

const clearanceLabels: Record<FlightClearanceStatus, string> = {
  PENDING_INSPECTION: "점검 대기",
  CLEARED: "비행 허가",
  GROUNDED: "비행 금지",
};

const MIN_RESOLUTION_NOTE_LENGTH = 3;
const MAX_RESOLUTION_NOTE_LENGTH = 200;
const MAX_MAINTENANCE_TEXT_LENGTH = 1000;

type MaintenanceClosureDecision =
  | "RETURN_TO_SERVICE"
  | "KEEP_GROUNDED";

interface MaintenanceSlaIncidentTrackingPanelProps {
  refreshKey: number;
}

interface ActionFeedback {
  tone: "success" | "error";
  message: string;
}

async function responseMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (
      typeof body === "object" &&
      body !== null &&
      "message" in body &&
      typeof body.message === "string"
    ) {
      return body.message;
    }
  } catch {
    // JSON 오류 본문이 아니면 기본 문구를 사용합니다.
  }
  return fallback;
}

async function fetchTracking(): Promise<MaintenanceSlaIncidentTracking> {
  const response = await fetch(
    "/api/maintenance/sla/incidents?windowDays=30",
    {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    },
  );
  if (!response.ok) {
    throw new Error(
      `SLA Incident 추적 조회 실패: HTTP ${response.status}`,
    );
  }

  const parsed = parseMaintenanceSlaIncidentTracking(
    await response.json() as unknown,
  );
  if (!parsed) {
    throw new Error(
      "SLA Incident 추적 응답 형식이 올바르지 않습니다.",
    );
  }
  return parsed;
}

export function MaintenanceSlaIncidentTrackingPanel({
  refreshKey,
}: MaintenanceSlaIncidentTrackingPanelProps) {
  const { status: operatorStatus, canOperate, operateDeniedReason } =
    useOperatorAccess();
  const [tracking, setTracking] =
    useState<MaintenanceSlaIncidentTracking | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [busyIncidentId, setBusyIncidentId] = useState<number | null>(
    null,
  );
  const [resolutionWorkOrderId, setResolutionWorkOrderId] = useState<
    number | null
  >(null);
  const [resolutionNote, setResolutionNote] = useState("");
  const [actionFeedback, setActionFeedback] =
    useState<ActionFeedback | null>(null);
  const mutationBusyRef = useRef(false);

  useEffect(() => {
    let active = true;

    fetchTracking()
      .then((parsed) => {
        if (active) {
          setTracking(parsed);
          setErrorMessage(null);
        }
      })
      .catch((error: unknown) => {
        if (active) {
          setErrorMessage(
            error instanceof Error
              ? error.message
              : "SLA Incident 추적 정보를 불러오지 못했습니다.",
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

  const startResponse = useCallback(
    async (item: MaintenanceSlaIncidentTrackingItem) => {
      const actor = operatorStatus?.username?.trim();
      if (!canOperate || !actor) {
        setActionFeedback({
          tone: "error",
          message:
            operateDeniedReason ??
            "OPERATOR 이상의 운영자 로그인이 필요합니다.",
        });
        return;
      }
      if (mutationBusyRef.current) return;

      mutationBusyRef.current = true;
      setBusyIncidentId(item.incidentId);
      setActionFeedback(null);
      try {
        if (item.incidentStatus !== "IN_PROGRESS") {
          const statusResponse = await fetch(
            `/api/incidents/${item.incidentId}/status`,
            {
              method: "PATCH",
              headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                status: "IN_PROGRESS",
                actor,
                note: "정비 SLA 자동 상향 Incident 대응 시작",
              }),
            },
          );
          if (!statusResponse.ok) {
            throw new Error(
              await responseMessage(
                statusResponse,
                `대응 시작 실패: HTTP ${statusResponse.status}`,
              ),
            );
          }
        }

        const assignResponse = await fetch(
          `/api/incidents/${item.incidentId}/assignee`,
          {
            method: "PATCH",
            headers: {
              Accept: "application/json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              assignee: actor,
              actor,
            }),
          },
        );
        if (!assignResponse.ok) {
          throw new Error(
            await responseMessage(
              assignResponse,
              `담당자 지정 실패: HTTP ${assignResponse.status}`,
            ),
          );
        }

        setActionFeedback({
          tone: "success",
          message: `Incident #${item.incidentId} 담당자 지정과 대응 시작을 완료했습니다.`,
        });
        try {
          setTracking(await fetchTracking());
          setErrorMessage(null);
        } catch (refreshError) {
          setErrorMessage(
            refreshError instanceof Error
              ? refreshError.message
              : "완료된 대응 상태를 다시 불러오지 못했습니다.",
          );
        }
      } catch (error) {
        setActionFeedback({
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Incident 대응 시작 중 오류가 발생했습니다.",
        });
        try {
          setTracking(await fetchTracking());
        } catch {
          // 부분 성공 여부는 다음 자동/수동 갱신에서 다시 확인합니다.
        }
      } finally {
        mutationBusyRef.current = false;
        setBusyIncidentId(null);
      }
    },
    [
      canOperate,
      operateDeniedReason,
      operatorStatus?.username,
    ],
  );

  const openResolution = useCallback(
    (item: MaintenanceSlaIncidentTrackingItem) => {
      if (!canOperate || !operatorStatus?.username?.trim()) {
        setActionFeedback({
          tone: "error",
          message:
            operateDeniedReason ??
            "OPERATOR 이상의 운영자 로그인이 필요합니다.",
        });
        return;
      }
      setResolutionWorkOrderId(item.workOrderId);
      setResolutionNote("");
      setActionFeedback(null);
    },
    [
      canOperate,
      operateDeniedReason,
      operatorStatus?.username,
    ],
  );

  const cancelResolution = useCallback(() => {
    setResolutionWorkOrderId(null);
    setResolutionNote("");
  }, []);

  const resolveIncident = useCallback(
    async (
      item: MaintenanceSlaIncidentTrackingItem,
      note: string,
    ) => {
      const actor = operatorStatus?.username?.trim();
      if (!canOperate || !actor) {
        setActionFeedback({
          tone: "error",
          message:
            operateDeniedReason ??
            "OPERATOR 이상의 운영자 로그인이 필요합니다.",
        });
        return;
      }

      const normalizedNote = note.trim();
      if (
        normalizedNote.length < MIN_RESOLUTION_NOTE_LENGTH ||
        normalizedNote.length > MAX_RESOLUTION_NOTE_LENGTH
      ) {
        setActionFeedback({
          tone: "error",
          message: `조치 메모를 ${MIN_RESOLUTION_NOTE_LENGTH}~${MAX_RESOLUTION_NOTE_LENGTH}자로 입력하세요.`,
        });
        return;
      }
      if (mutationBusyRef.current) return;

      mutationBusyRef.current = true;
      setBusyIncidentId(item.incidentId);
      setActionFeedback(null);
      try {
        const response = await fetch(
          `/api/incidents/${item.incidentId}/status`,
          {
            method: "PATCH",
            headers: {
              Accept: "application/json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              status: "RESOLVED",
              actor,
              note: `정비 SLA 조치 완료: ${normalizedNote}`,
            }),
          },
        );
        if (!response.ok) {
          throw new Error(
            await responseMessage(
              response,
              `Incident 해결 처리 실패: HTTP ${response.status}`,
            ),
          );
        }

        setResolutionWorkOrderId(null);
        setResolutionNote("");
        setActionFeedback({
          tone: "success",
          message: `Incident #${item.incidentId} 조치 완료를 기록했습니다.`,
        });
        try {
          setTracking(await fetchTracking());
          setErrorMessage(null);
        } catch (refreshError) {
          setErrorMessage(
            refreshError instanceof Error
              ? refreshError.message
              : "완료된 Incident 상태를 다시 불러오지 못했습니다.",
          );
        }
      } catch (error) {
        setActionFeedback({
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "Incident 해결 처리 중 오류가 발생했습니다.",
        });
        try {
          setTracking(await fetchTracking());
        } catch {
          // 실패한 변경의 서버 상태는 다음 자동/수동 갱신에서 확인합니다.
        }
      } finally {
        mutationBusyRef.current = false;
        setBusyIncidentId(null);
      }
    },
    [
      canOperate,
      operateDeniedReason,
      operatorStatus?.username,
    ],
  );

  const completeWorkOrder = useCallback(
    async (
      item: MaintenanceSlaIncidentTrackingItem,
      finding: string,
      resolutionNote: string,
      decision: MaintenanceClosureDecision,
    ): Promise<boolean> => {
      const actor = operatorStatus?.username?.trim();
      if (!canOperate || !actor) {
        setActionFeedback({
          tone: "error",
          message:
            operateDeniedReason ??
            "OPERATOR 이상의 운영자 로그인이 필요합니다.",
        });
        return false;
      }

      const normalizedFinding = finding.trim();
      const normalizedResolutionNote = resolutionNote.trim();
      if (!normalizedFinding || !normalizedResolutionNote) {
        setActionFeedback({
          tone: "error",
          message: "점검 결과와 조치 메모를 모두 입력하세요.",
        });
        return false;
      }
      if (
        normalizedFinding.length > MAX_MAINTENANCE_TEXT_LENGTH ||
        normalizedResolutionNote.length >
          MAX_MAINTENANCE_TEXT_LENGTH
      ) {
        setActionFeedback({
          tone: "error",
          message: `점검 결과와 조치 메모는 각각 ${MAX_MAINTENANCE_TEXT_LENGTH}자 이하여야 합니다.`,
        });
        return false;
      }
      if (
        item.responseStatus !== "COMPLETED" ||
        item.workOrderStatus !== "IN_PROGRESS"
      ) {
        setActionFeedback({
          tone: "error",
          message:
            "Incident 해결 후 진행 중인 정비 작업만 마감할 수 있습니다.",
        });
        return false;
      }
      if (mutationBusyRef.current) return false;

      mutationBusyRef.current = true;
      setBusyIncidentId(item.incidentId);
      setActionFeedback(null);
      try {
        const response = await fetch(
          `/api/maintenance/work-orders/${item.workOrderId}/complete`,
          {
            method: "PATCH",
            headers: {
              Accept: "application/json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              decision,
              finding: normalizedFinding,
              resolutionNote: normalizedResolutionNote,
              actor,
            }),
          },
        );
        if (!response.ok) {
          throw new Error(
            await responseMessage(
              response,
              `정비 작업 마감 실패: HTTP ${response.status}`,
            ),
          );
        }

        setActionFeedback({
          tone: "success",
          message:
            decision === "RETURN_TO_SERVICE"
              ? `작업 #${item.workOrderId} 마감과 Drone #${item.droneId} 재운항 승인을 완료했습니다.`
              : `작업 #${item.workOrderId}을 마감하고 Drone #${item.droneId} 운항 중지를 유지했습니다.`,
        });
        try {
          setTracking(await fetchTracking());
          setErrorMessage(null);
        } catch (refreshError) {
          setErrorMessage(
            refreshError instanceof Error
              ? refreshError.message
              : "마감된 정비 작업 상태를 다시 불러오지 못했습니다.",
          );
        }
        return true;
      } catch (error) {
        setActionFeedback({
          tone: "error",
          message:
            error instanceof Error
              ? error.message
              : "정비 작업 마감 중 오류가 발생했습니다.",
        });
        try {
          setTracking(await fetchTracking());
        } catch {
          // 실패한 변경의 서버 상태는 다음 자동/수동 갱신에서 확인합니다.
        }
        return false;
      } finally {
        mutationBusyRef.current = false;
        setBusyIncidentId(null);
      }
    },
    [
      canOperate,
      operateDeniedReason,
      operatorStatus?.username,
    ],
  );

  if (loading && tracking === null) {
    return (
      <section
        data-maintenance-sla-incident-tracking
        data-maintenance-sla-response-queue
        data-maintenance-sla-inline-action
        data-maintenance-sla-inline-resolution
        data-maintenance-sla-workorder-closure
        data-maintenance-sla-closure-consistency
        className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-600 shadow-sm"
      >
        정비 작업과 SLA Incident 연결 이력을 확인하고 있습니다.
      </section>
    );
  }

  if (tracking === null) {
    return (
      <section
        data-maintenance-sla-incident-tracking
        data-maintenance-sla-response-queue
        data-maintenance-sla-inline-action
        data-maintenance-sla-inline-resolution
        data-maintenance-sla-workorder-closure
        data-maintenance-sla-closure-consistency
        role="alert"
        className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-5 text-sm font-bold text-red-900"
      >
        {errorMessage ?? "SLA Incident 연결 이력을 표시할 수 없습니다."}
      </section>
    );
  }

  return (
    <section
      data-maintenance-sla-incident-tracking
      data-maintenance-sla-inline-action
      data-maintenance-sla-inline-resolution
      data-maintenance-sla-workorder-closure
      data-maintenance-sla-closure-consistency
      className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.16em] text-violet-700">
            SLA Incident Trace
          </p>
          <h2 className="mt-1 text-xl font-black text-slate-950">
            정비 SLA Incident 추적
          </h2>
          <p className="mt-1 text-xs text-slate-500">
            최근 {tracking.windowDays}일 ·{" "}
            {formatKoreanDateTime(tracking.evaluatedAt)}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 text-center text-xs sm:grid-cols-4">
          <TrackingCounter
            label="작업"
            value={tracking.totalWorkOrders}
            style="bg-slate-100 text-slate-900"
          />
          <TrackingCounter
            label="Incident 연결"
            value={tracking.connectedIncidents}
            style="bg-sky-50 text-sky-900"
          />
          <TrackingCounter
            label="SLA 초과"
            value={tracking.overdueWorkOrders}
            style="bg-rose-50 text-rose-900"
          />
          <TrackingCounter
            label="자동 상향"
            value={tracking.escalatedIncidents}
            style="bg-violet-50 text-violet-900"
          />
        </div>
      </div>

      <div
        data-maintenance-sla-response-queue
        className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-black text-slate-950">
              운영자 대응 큐
            </h3>
            <p className="mt-0.5 text-xs text-slate-500">
              자동 상향 이후 담당자 지정과 Incident 조치 진행 상태
            </p>
          </div>
          <p className="text-xs font-bold text-slate-600">
            감시 중 {tracking.monitoringWorkOrders}건
          </p>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2 text-center text-xs sm:grid-cols-4">
          <TrackingCounter
            label="상향 대기"
            value={tracking.escalationPendingIncidents}
            style="bg-rose-100 text-rose-900"
          />
          <TrackingCounter
            label="담당자 필요"
            value={tracking.assignmentRequiredIncidents}
            style="bg-orange-100 text-orange-900"
          />
          <TrackingCounter
            label="대응 중"
            value={tracking.inResponseIncidents}
            style="bg-violet-100 text-violet-900"
          />
          <TrackingCounter
            label="조치 종료"
            value={tracking.completedResponses}
            style="bg-emerald-100 text-emerald-900"
          />
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-cyan-200 bg-cyan-50 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-black text-cyan-950">
              마감 정합성
            </h3>
            <p className="mt-0.5 text-xs text-cyan-900">
              Incident·정비 작업·비행 허가의 최종 상태 조합
            </p>
          </div>
          <p
            className={`text-xs font-black ${
              tracking.closureConsistencyAlerts > 0
                ? "text-red-800"
                : "text-emerald-800"
            }`}
          >
            정합성 경고 {tracking.closureConsistencyAlerts}건
          </p>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2 text-center text-xs sm:grid-cols-4">
          <TrackingCounter
            label="정비 마감 필요"
            value={tracking.pendingWorkOrderClosures}
            style="bg-amber-100 text-amber-900"
          />
          <TrackingCounter
            label="재운항 확인"
            value={tracking.returnToServiceConfirmed}
            style="bg-emerald-100 text-emerald-900"
          />
          <TrackingCounter
            label="운항 중지"
            value={tracking.groundedClosures}
            style="bg-rose-100 text-rose-900"
          />
          <TrackingCounter
            label="수동 점검"
            value={tracking.closureConsistencyAlerts}
            style="bg-red-100 text-red-900"
          />
        </div>
      </div>

      {errorMessage && (
        <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs font-bold text-amber-900">
          최신 값 갱신 실패: {errorMessage}
        </p>
      )}

      {actionFeedback && (
        <p
          role={actionFeedback.tone === "error" ? "alert" : "status"}
          className={`mt-4 rounded-xl border p-3 text-xs font-bold ${
            actionFeedback.tone === "error"
              ? "border-red-200 bg-red-50 text-red-900"
              : "border-sky-200 bg-sky-50 text-sky-900"
          }`}
        >
          {actionFeedback.message}
        </p>
      )}

      {tracking.items.length === 0 ? (
        <p className="mt-5 rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
          최근 {tracking.windowDays}일 이내 정비 작업이 없습니다.
        </p>
      ) : (
        <div className="mt-5 space-y-3">
          {tracking.items.map((item) => (
            <TrackingRow
              key={item.workOrderId}
              item={item}
              canOperate={canOperate}
              deniedReason={operateDeniedReason}
              busy={busyIncidentId === item.incidentId}
              actionsLocked={busyIncidentId !== null}
              resolutionOpen={
                resolutionWorkOrderId === item.workOrderId
              }
              resolutionNote={resolutionNote}
              onStartResponse={startResponse}
              onOpenResolution={openResolution}
              onCancelResolution={cancelResolution}
              onResolutionNoteChange={setResolutionNote}
              onResolveIncident={resolveIncident}
              onCompleteWorkOrder={completeWorkOrder}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function TrackingRow({
  item,
  canOperate,
  deniedReason,
  busy,
  actionsLocked,
  resolutionOpen,
  resolutionNote,
  onStartResponse,
  onOpenResolution,
  onCancelResolution,
  onResolutionNoteChange,
  onResolveIncident,
  onCompleteWorkOrder,
}: {
  item: MaintenanceSlaIncidentTrackingItem;
  canOperate: boolean;
  deniedReason: string | null;
  busy: boolean;
  actionsLocked: boolean;
  resolutionOpen: boolean;
  resolutionNote: string;
  onStartResponse: (
    item: MaintenanceSlaIncidentTrackingItem,
  ) => Promise<void>;
  onOpenResolution: (
    item: MaintenanceSlaIncidentTrackingItem,
  ) => void;
  onCancelResolution: () => void;
  onResolutionNoteChange: (value: string) => void;
  onResolveIncident: (
    item: MaintenanceSlaIncidentTrackingItem,
    note: string,
  ) => Promise<void>;
  onCompleteWorkOrder: (
    item: MaintenanceSlaIncidentTrackingItem,
    finding: string,
    resolutionNote: string,
    decision: MaintenanceClosureDecision,
  ) => Promise<boolean>;
}) {
  const resolutionFormId =
    `maintenance-resolution-${item.workOrderId}`;
  const closureFormId =
    `maintenance-workorder-closure-${item.workOrderId}`;
  const [closureOpen, setClosureOpen] = useState(false);
  const [finding, setFinding] = useState("");
  const [maintenanceNote, setMaintenanceNote] = useState("");
  const [decision, setDecision] =
    useState<MaintenanceClosureDecision>("RETURN_TO_SERVICE");
  const [safetyConfirmed, setSafetyConfirmed] = useState(false);

  function closeClosureForm() {
    setClosureOpen(false);
    setFinding("");
    setMaintenanceNote("");
    setDecision("RETURN_TO_SERVICE");
    setSafetyConfirmed(false);
  }

  return (
    <article className="rounded-xl border border-slate-200 p-4">
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_auto] lg:items-center">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-black text-slate-800">
              작업 #{item.workOrderId}
            </span>
            <span className="text-sm font-black text-slate-950">
              Drone #{item.droneId}
            </span>
            {item.escalated && (
              <span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-black text-violet-900">
                자동 상향 완료
              </span>
            )}
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-black ${responseStyles[item.responseStatus]}`}
            >
              {responseLabels[item.responseStatus]}
            </span>
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-black ${closureStyles[item.closureStatus]}`}
            >
              {closureLabels[item.closureStatus]}
            </span>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            Incident #{item.incidentId} · 작업{" "}
            {workOrderLabels[item.workOrderStatus]} · 허가{" "}
            {clearanceLabels[item.flightClearanceStatus]}
          </p>
          <p className="mt-1 text-xs font-bold text-slate-600">
            담당자 {item.incidentAssignee ?? "미지정"}
          </p>
        </div>

        <div>
          <p className="text-sm font-bold text-slate-900">
            {item.incidentTitle ??
              "연결 Incident를 찾을 수 없습니다."}
          </p>
          <p className="mt-1 text-xs text-slate-600">
            {formatIncidentState(item)}
            {" · "}
            {formatSlaState(item)}
          </p>
          {item.escalatedAt && (
            <p className="mt-1 text-xs font-bold text-violet-800">
              {formatKoreanDateTime(item.escalatedAt)} 자동 상향
              {item.escalationNote
                ? ` · ${item.escalationNote}`
                : ""}
            </p>
          )}
          <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-xs font-bold text-slate-700">
            다음 조치: {item.recommendedAction}
          </p>
          <p
            className={`mt-2 rounded-lg px-3 py-2 text-xs font-bold ${
              item.closureStatus === "REVIEW_REQUIRED"
                ? "bg-red-50 text-red-900"
                : item.closureStatus === "WORK_ORDER_PENDING"
                  ? "bg-amber-50 text-amber-900"
                  : "bg-cyan-50 text-cyan-900"
            }`}
          >
            마감 권고: {item.closureRecommendedAction}
          </p>
        </div>

        <div className="flex flex-wrap gap-2 justify-self-start lg:justify-self-end">
          {item.responseStatus === "ASSIGNMENT_REQUIRED" && (
            <button
              type="button"
              disabled={!canOperate || actionsLocked}
              title={
                canOperate
                  ? "현재 로그인 운영자를 담당자로 지정합니다."
                  : (deniedReason ?? undefined)
              }
              onClick={() => void onStartResponse(item)}
              className="rounded-lg bg-orange-700 px-3 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? "처리 중..." : "내가 담당·대응 시작"}
            </button>
          )}
          {item.responseStatus === "IN_RESPONSE" && (
            <button
              type="button"
              aria-expanded={resolutionOpen}
              aria-controls={resolutionFormId}
              disabled={!canOperate || actionsLocked}
              title={
                canOperate
                  ? "조치 메모를 남기고 Incident를 해결 처리합니다."
                  : (deniedReason ?? undefined)
              }
              onClick={() => onOpenResolution(item)}
              className="rounded-lg bg-emerald-700 px-3 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              조치 완료
            </button>
          )}
          {item.responseStatus === "COMPLETED" &&
            item.workOrderStatus === "IN_PROGRESS" && (
              <button
                type="button"
                aria-expanded={closureOpen}
                aria-controls={closureFormId}
                disabled={!canOperate || actionsLocked}
                title={
                  canOperate
                    ? "점검 결과와 비행 허가 판정을 기록합니다."
                    : (deniedReason ?? undefined)
                }
                onClick={() => setClosureOpen(true)}
                className="rounded-lg bg-cyan-700 px-3 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                정비 작업 마감
              </button>
            )}
          {item.responseStatus !== "COMPLETED" && (
            <Link
              href={`/dashboard?droneId=${item.droneId}`}
              className="rounded-lg bg-slate-950 px-3 py-2 text-sm font-bold text-white"
            >
              운영 조치 열기
            </Link>
          )}
          {(
            item.closureStatus === "REVIEW_REQUIRED" ||
            (
              item.closureStatus === "WORK_ORDER_PENDING" &&
              item.workOrderStatus !== "IN_PROGRESS"
            )
          ) && (
            <Link
              href={`/maintenance?workOrderId=${item.workOrderId}`}
              className="rounded-lg border border-cyan-300 bg-cyan-50 px-3 py-2 text-sm font-bold text-cyan-900"
            >
              정비 작업 점검
            </Link>
          )}
          <Link
            href={`/incidents/${item.incidentId}/report`}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-bold text-slate-700"
          >
            Incident 보고서
          </Link>
        </div>
      </div>

      {resolutionOpen && item.responseStatus === "IN_RESPONSE" && (
        <form
          id={resolutionFormId}
          data-maintenance-sla-resolution-form
          className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4"
          onSubmit={(event) => {
            event.preventDefault();
            void onResolveIncident(item, resolutionNote);
          }}
        >
          <label
            htmlFor={`${resolutionFormId}-note`}
            className="text-sm font-black text-emerald-950"
          >
            Incident 조치 완료 메모
          </label>
          <textarea
            id={`${resolutionFormId}-note`}
            value={resolutionNote}
            minLength={MIN_RESOLUTION_NOTE_LENGTH}
            maxLength={MAX_RESOLUTION_NOTE_LENGTH}
            required
            disabled={!canOperate || actionsLocked}
            onChange={(event) =>
              onResolutionNoteChange(event.target.value)
            }
            placeholder="확인한 원인과 완료한 조치를 입력하세요."
            className="mt-2 min-h-24 w-full resize-y rounded-lg border border-emerald-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-emerald-600"
          />
          <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-emerald-900">
              {resolutionNote.length}/{MAX_RESOLUTION_NOTE_LENGTH}자
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={onCancelResolution}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-bold text-slate-700 disabled:opacity-50"
              >
                취소
              </button>
              <button
                type="submit"
                disabled={
                  !canOperate ||
                  actionsLocked ||
                  resolutionNote.trim().length <
                    MIN_RESOLUTION_NOTE_LENGTH
                }
                className="rounded-lg bg-emerald-800 px-3 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy ? "처리 중..." : "해결 처리 확정"}
              </button>
            </div>
          </div>
        </form>
      )}

      {closureOpen &&
        item.responseStatus === "COMPLETED" &&
        item.workOrderStatus === "IN_PROGRESS" && (
          <form
            id={closureFormId}
            data-maintenance-sla-workorder-closure-form
            className="mt-4 grid gap-3 rounded-xl border border-cyan-200 bg-cyan-50 p-4 md:grid-cols-2"
            onSubmit={(event) => {
              event.preventDefault();
              void onCompleteWorkOrder(
                item,
                finding,
                maintenanceNote,
                decision,
              ).then((completed) => {
                if (completed) closeClosureForm();
              });
            }}
          >
            <div className="md:col-span-2">
              <h3 className="text-sm font-black text-cyan-950">
                정비 작업 마감 및 비행 허가 판정
              </h3>
              <p className="mt-1 text-xs leading-5 text-cyan-900">
                재운항 승인은 비행 게이트를 CLEARED로 변경하고, 운항
                중지 유지는 GROUNDED 상태를 유지합니다.
              </p>
            </div>
            <label className="text-sm font-bold text-slate-800">
              점검 결과
              <textarea
                value={finding}
                maxLength={MAX_MAINTENANCE_TEXT_LENGTH}
                rows={3}
                required
                disabled={!canOperate || actionsLocked}
                onChange={(event) => setFinding(event.target.value)}
                placeholder="기체·배터리·통신·센서 점검 결과"
                className="mt-1 block w-full rounded-lg border border-cyan-300 bg-white p-3 font-normal"
              />
            </label>
            <label className="text-sm font-bold text-slate-800">
              조치 메모
              <textarea
                value={maintenanceNote}
                maxLength={MAX_MAINTENANCE_TEXT_LENGTH}
                rows={3}
                required
                disabled={!canOperate || actionsLocked}
                onChange={(event) =>
                  setMaintenanceNote(event.target.value)
                }
                placeholder="수리·교체·재시험 및 판정 근거"
                className="mt-1 block w-full rounded-lg border border-cyan-300 bg-white p-3 font-normal"
              />
            </label>
            <label className="text-sm font-bold text-slate-800">
              최종 판정
              <select
                value={decision}
                disabled={!canOperate || actionsLocked}
                onChange={(event) =>
                  setDecision(
                    event.target.value as MaintenanceClosureDecision,
                  )
                }
                className="mt-1 block w-full rounded-lg border border-cyan-300 bg-white px-3 py-2 font-normal"
              >
                <option value="RETURN_TO_SERVICE">
                  재운항 승인
                </option>
                <option value="KEEP_GROUNDED">
                  운항 중지 유지
                </option>
              </select>
            </label>
            <label className="flex items-start gap-2 rounded-lg border border-cyan-200 bg-white p-3 text-xs font-bold leading-5 text-slate-700">
              <input
                type="checkbox"
                checked={safetyConfirmed}
                disabled={!canOperate || actionsLocked}
                onChange={(event) =>
                  setSafetyConfirmed(event.target.checked)
                }
                className="mt-1"
              />
              점검 결과와 판정 근거를 확인했으며 이 결정이 비행
              게이트에 반영됨을 이해했습니다.
            </label>
            <div className="flex flex-wrap justify-end gap-2 md:col-span-2">
              <button
                type="button"
                disabled={busy}
                onClick={closeClosureForm}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-bold text-slate-700 disabled:opacity-50"
              >
                취소
              </button>
              <button
                type="submit"
                disabled={
                  !canOperate ||
                  actionsLocked ||
                  !safetyConfirmed ||
                  !finding.trim() ||
                  !maintenanceNote.trim()
                }
                className="rounded-lg bg-cyan-800 px-3 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy ? "저장 중..." : "정비 마감 확정"}
              </button>
            </div>
          </form>
        )}
    </article>
  );
}

function TrackingCounter({
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
      <p className="mt-0.5 text-lg font-black">{value}건</p>
    </div>
  );
}

function formatIncidentState(
  item: MaintenanceSlaIncidentTrackingItem,
): string {
  if (
    item.incidentStatus === null ||
    item.incidentPriority === null
  ) {
    return "Incident 연결 누락";
  }

  return `${statusLabels[item.incidentStatus]} · ${
    priorityLabels[item.incidentPriority]
  }`;
}

function formatSlaState(
  item: MaintenanceSlaIncidentTrackingItem,
): string {
  if (
    item.slaStatus === "OVERDUE" &&
    item.slaOverdueMinutes !== null
  ) {
    return `SLA ${formatMinutes(item.slaOverdueMinutes)} 초과`;
  }
  if (item.slaStatus === "DUE_SOON") return "SLA 임박";
  if (item.slaStatus === "ON_TRACK") return "SLA 정상";
  return "SLA 종료";
}

function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes}분`;
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)}시간`;
  return `${Math.floor(minutes / (24 * 60))}일`;
}
