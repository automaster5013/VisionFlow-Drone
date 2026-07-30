"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { MaintenanceMetricsPanel } from "@/components/maintenance/maintenance-metrics-panel";
import { MaintenancePriorityPanel } from "@/components/maintenance/maintenance-priority-panel";
import { useOperatorAccess } from "@/components/security/operator-access-provider";
import { formatKoreanDateTime } from "@/lib/date";
import {
  parseMaintenanceFlightClearance,
  type MaintenanceFlightClearance,
} from "@/types/maintenance-flight-clearance";
import {
  parseMaintenanceWorkOrderDetail,
  parseMaintenanceWorkOrders,
  type MaintenanceCompletionDecision,
  type MaintenanceWorkOrder,
  type MaintenanceWorkOrderActionType,
  type MaintenanceWorkOrderDetail,
  type MaintenanceWorkOrderStatus,
} from "@/types/maintenance-work-order";

const statusLabels: Record<MaintenanceWorkOrderStatus, string> = {
  OPEN: "점검 대기",
  IN_PROGRESS: "점검 중",
  COMPLETED: "재운항 승인",
  GROUNDED: "운항 중지",
};

const statusStyles: Record<MaintenanceWorkOrderStatus, string> = {
  OPEN: "border-amber-200 bg-amber-50 text-amber-900",
  IN_PROGRESS: "border-sky-200 bg-sky-50 text-sky-900",
  COMPLETED: "border-emerald-200 bg-emerald-50 text-emerald-900",
  GROUNDED: "border-rose-200 bg-rose-50 text-rose-900",
};

const actionLabels: Record<MaintenanceWorkOrderActionType, string> = {
  CREATED: "작업 생성",
  RISK_SYNCHRONIZED: "위험 정보 동기화",
  REOPENED: "작업 재개",
  INSPECTION_STARTED: "점검 시작",
  RETURNED_TO_SERVICE: "재운항 승인",
  GROUNDED: "운항 중지",
};

interface WorkOrderEvidence {
  detail: MaintenanceWorkOrderDetail;
  clearance: MaintenanceFlightClearance | null;
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

interface MaintenanceWorkOrderBoardProps {
  initialDroneId?: number | null;
  initialWorkOrderId?: number | null;
  initialStatus?: MaintenanceWorkOrderStatus | null;
}

export function MaintenanceWorkOrderBoard({
  initialDroneId = null,
  initialWorkOrderId = null,
  initialStatus = null,
}: MaintenanceWorkOrderBoardProps) {
  const { status: operatorStatus, canOperate, operateDeniedReason } =
    useOperatorAccess();
  const [orders, setOrders] = useState<MaintenanceWorkOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [metricsRevision, setMetricsRevision] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(
    initialWorkOrderId,
  );
  const [evidenceById, setEvidenceById] = useState<
    Record<number, WorkOrderEvidence>
  >({});
  const [evidenceLoadingId, setEvidenceLoadingId] =
    useState<number | null>(null);
  const [evidenceErrorById, setEvidenceErrorById] = useState<
    Record<number, string>
  >({});

  const actor = operatorStatus?.username?.trim() || "local-operator";
  const ordersEndpoint = useMemo(() => {
    const query = new URLSearchParams({ limit: "200" });
    if (initialDroneId !== null) {
      query.set("droneId", String(initialDroneId));
    }
    if (initialStatus !== null) {
      query.set("status", initialStatus);
    }
    return `/api/maintenance/work-orders?${query}`;
  }, [initialDroneId, initialStatus]);

  const loadOrders = useCallback(async () => {
    const response = await fetch(ordersEndpoint, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(
        await responseMessage(
          response,
          `점검 작업지시 조회 실패: HTTP ${response.status}`,
        ),
      );
    }
    const body: unknown = await response.json();
    const parsed = parseMaintenanceWorkOrders(body);
    if (!parsed) {
      throw new Error("점검 작업지시 응답 형식이 올바르지 않습니다.");
    }
    setOrders(parsed);
  }, [ordersEndpoint]);

  const loadEvidence = useCallback(
    async (orderId: number, droneId: number) => {
      const detailResponse = await fetch(
        `/api/maintenance/work-orders/${orderId}`,
        {
          headers: { Accept: "application/json" },
          cache: "no-store",
        },
      );
      if (!detailResponse.ok) {
        throw new Error(
          await responseMessage(
            detailResponse,
            `점검 처리 이력 조회 실패: HTTP ${detailResponse.status}`,
          ),
        );
      }

      const detail = parseMaintenanceWorkOrderDetail(
        await detailResponse.json() as unknown,
      );
      if (!detail) {
        throw new Error("점검 처리 이력 응답 형식이 올바르지 않습니다.");
      }

      let clearance: MaintenanceFlightClearance | null = null;
      try {
        const clearanceResponse = await fetch(
          `/api/maintenance/flight-clearance/${droneId}`,
          {
            headers: { Accept: "application/json" },
            cache: "no-store",
          },
        );
        if (clearanceResponse.ok) {
          clearance = parseMaintenanceFlightClearance(
            await clearanceResponse.json() as unknown,
          );
        }
      } catch {
        // 이력은 표시하고 비행 허가 검증만 조회 불가로 처리합니다.
      }

      const evidence = { detail, clearance };
      setEvidenceById((current) => ({
        ...current,
        [orderId]: evidence,
      }));
      return evidence;
    },
    [],
  );

  useEffect(() => {
    let active = true;

    fetch(ordersEndpoint, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(
            await responseMessage(
              response,
              `점검 작업지시 조회 실패: HTTP ${response.status}`,
            ),
          );
        }
        return response.json() as Promise<unknown>;
      })
      .then((body) => {
        const parsed = parseMaintenanceWorkOrders(body);
        if (!parsed) {
          throw new Error("점검 작업지시 응답 형식이 올바르지 않습니다.");
        }
        if (active) setOrders(parsed);
      })
      .catch((error: unknown) => {
        if (active) {
          setErrorMessage(
            error instanceof Error
              ? error.message
              : "점검 작업지시를 불러오지 못했습니다.",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [ordersEndpoint]);

  useEffect(() => {
    if (loading || initialWorkOrderId === null) {
      return;
    }

    const timerId = window.setTimeout(() => {
      document
        .getElementById(`maintenance-work-order-${initialWorkOrderId}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 0);

    return () => {
      window.clearTimeout(timerId);
    };
  }, [initialWorkOrderId, loading, orders]);

  useEffect(() => {
    if (
      loading ||
      initialWorkOrderId === null ||
      evidenceById[initialWorkOrderId]
    ) {
      return;
    }
    const focusedOrder = orders.find(
      (order) => order.id === initialWorkOrderId,
    );
    if (!focusedOrder) {
      return;
    }

    const timerId = window.setTimeout(() => {
      setEvidenceLoadingId(initialWorkOrderId);
      void loadEvidence(initialWorkOrderId, focusedOrder.droneId)
        .catch((error: unknown) => {
          setEvidenceErrorById((current) => ({
            ...current,
            [initialWorkOrderId]:
              error instanceof Error
                ? error.message
                : "점검 처리 이력을 불러오지 못했습니다.",
          }));
        })
        .finally(() => {
          setEvidenceLoadingId((current) =>
            current === initialWorkOrderId ? null : current,
          );
        });
    }, 0);

    return () => {
      window.clearTimeout(timerId);
    };
  }, [
    evidenceById,
    initialWorkOrderId,
    loadEvidence,
    loading,
    orders,
  ]);

  const counters = useMemo(
    () => ({
      open: orders.filter((order) => order.status === "OPEN").length,
      inProgress: orders.filter((order) => order.status === "IN_PROGRESS")
        .length,
      cleared: orders.filter((order) => order.status === "COMPLETED").length,
      grounded: orders.filter((order) => order.status === "GROUNDED").length,
    }),
    [orders],
  );

  async function mutate(
    orderId: number,
    action: "start" | "complete",
    body: Record<string, unknown>,
    successMessage: string,
  ) {
    if (!canOperate || busyId !== null) return;
    setBusyId(orderId);
    setErrorMessage(null);
    setMessage(null);

    try {
      const response = await fetch(
        `/api/maintenance/work-orders/${orderId}/${action}`,
        {
          method: "PATCH",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
          body: JSON.stringify(body),
        },
      );
      if (!response.ok) {
        throw new Error(
          await responseMessage(
            response,
            `점검 작업 처리 실패: HTTP ${response.status}`,
          ),
        );
      }
      await loadOrders();
      setMetricsRevision((revision) => revision + 1);
      const changedOrder = orders.find((order) => order.id === orderId);
      if (expandedId === orderId && changedOrder) {
        try {
          await loadEvidence(orderId, changedOrder.droneId);
          setEvidenceErrorById((current) => {
            const next = { ...current };
            delete next[orderId];
            return next;
          });
        } catch (evidenceError) {
          setEvidenceErrorById((current) => ({
            ...current,
            [orderId]:
              evidenceError instanceof Error
                ? evidenceError.message
                : "변경 후 점검 이력을 갱신하지 못했습니다.",
          }));
        }
      }
      setMessage(successMessage);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "점검 작업을 처리하지 못했습니다.",
      );
    } finally {
      setBusyId(null);
    }
  }

  async function toggleEvidence(order: MaintenanceWorkOrder) {
    if (expandedId === order.id) {
      setExpandedId(null);
      return;
    }

    setExpandedId(order.id);
    if (evidenceById[order.id] || evidenceLoadingId !== null) {
      return;
    }

    setEvidenceLoadingId(order.id);
    setEvidenceErrorById((current) => {
      const next = { ...current };
      delete next[order.id];
      return next;
    });
    try {
      await loadEvidence(order.id, order.droneId);
    } catch (error) {
      setEvidenceErrorById((current) => ({
        ...current,
        [order.id]:
          error instanceof Error
            ? error.message
            : "점검 처리 이력을 불러오지 못했습니다.",
      }));
    } finally {
      setEvidenceLoadingId(null);
    }
  }

  async function synchronize() {
    if (!canOperate || syncing) return;
    setSyncing(true);
    setErrorMessage(null);
    setMessage(null);

    try {
      const response = await fetch(
        "/api/flight-quality/fleet-reliability/incidents/synchronize" +
          "?limitPerDrone=20",
        { method: "POST", headers: { Accept: "application/json" } },
      );
      if (!response.ok) {
        throw new Error(
          await responseMessage(
            response,
            `신뢰도 동기화 실패: HTTP ${response.status}`,
          ),
        );
      }
      await loadOrders();
      setMetricsRevision((revision) => revision + 1);
      setMessage("신뢰도 Incident와 점검 작업지시를 동기화했습니다.");
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "신뢰도 작업지시 동기화에 실패했습니다.",
      );
    } finally {
      setSyncing(false);
    }
  }

  async function complete(
    event: React.FormEvent<HTMLFormElement>,
    orderId: number,
  ) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const decision = form.get("decision") as MaintenanceCompletionDecision;
    const finding = String(form.get("finding") ?? "").trim();
    const resolutionNote = String(form.get("resolutionNote") ?? "").trim();

    if (!finding || !resolutionNote) {
      setErrorMessage("점검 결과와 조치 메모를 모두 입력하세요.");
      return;
    }

    await mutate(
      orderId,
      "complete",
      { decision, finding, resolutionNote, actor },
      decision === "RETURN_TO_SERVICE"
        ? `작업 #${orderId}의 재운항을 승인했습니다.`
        : `작업 #${orderId}의 운항 중지를 기록했습니다.`,
    );
  }

  return (
    <main className="min-h-screen bg-slate-100 px-4 py-8">
      <section className="mx-auto max-w-6xl">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-black uppercase tracking-[0.18em] text-cyan-700">
              Maintenance Operations
            </p>
            <h1 className="mt-2 text-3xl font-black text-slate-950">
              기체 점검 작업지시
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
              기체 신뢰도 Incident에서 자동 생성된 점검을 처리하고, 실제
              점검 결과와 재운항 승인 또는 운항 중지를 MySQL 이력으로
              남깁니다.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              href="/fleet-reliability"
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700"
            >
              기체 신뢰도
            </Link>
            <button
              type="button"
              onClick={synchronize}
              disabled={!canOperate || syncing}
              title={canOperate ? undefined : (operateDeniedReason ?? undefined)}
              className="rounded-lg bg-cyan-700 px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {syncing ? "동기화 중..." : "Incident·작업 동기화"}
            </button>
          </div>
        </header>

        <MaintenanceMetricsPanel refreshKey={metricsRevision} />
        <MaintenancePriorityPanel refreshKey={metricsRevision} />

        <h2 className="mt-8 text-lg font-black text-slate-950">
          현재 조회 결과
        </h2>
        <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Counter label="점검 대기" value={counters.open} />
          <Counter label="점검 중" value={counters.inProgress} />
          <Counter label="재운항 승인" value={counters.cleared} />
          <Counter label="운항 중지" value={counters.grounded} />
        </div>

        <form
          action="/maintenance"
          method="get"
          className="mt-5 grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
        >
          <label className="text-sm font-bold text-slate-700">
            드론 ID
            <input
              type="number"
              name="droneId"
              min={1}
              defaultValue={initialDroneId ?? ""}
              placeholder="전체 드론"
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal"
            />
          </label>
          <label className="text-sm font-bold text-slate-700">
            작업 상태
            <select
              name="status"
              defaultValue={initialStatus ?? ""}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 font-normal"
            >
              <option value="">전체 상태</option>
              <option value="OPEN">점검 대기</option>
              <option value="IN_PROGRESS">점검 중</option>
              <option value="COMPLETED">재운항 승인</option>
              <option value="GROUNDED">운항 중지</option>
            </select>
          </label>
          <div className="flex flex-wrap items-end gap-2">
            <button
              type="submit"
              className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-bold text-white"
            >
              조건 조회
            </button>
            <Link
              href="/maintenance"
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700"
            >
              초기화
            </Link>
          </div>
        </form>

        {(initialDroneId !== null || initialWorkOrderId !== null) && (
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-cyan-200 bg-cyan-50 p-4">
            <p className="text-sm font-bold text-cyan-950">
              관제 연결:
              {initialDroneId !== null ? ` Drone #${initialDroneId}` : ""}
              {initialWorkOrderId !== null
                ? ` · 작업 #${initialWorkOrderId}`
                : ""}
            </p>
            {initialDroneId !== null && (
              <Link
                href={`/drones?droneId=${initialDroneId}`}
                className="rounded-lg border border-cyan-300 bg-white px-3 py-2 text-sm font-bold text-cyan-800"
              >
                관제 지도로 돌아가기
              </Link>
            )}
          </div>
        )}

        {(message || errorMessage) && (
          <div className="mt-5 space-y-2">
            {message && (
              <p className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-bold text-emerald-900">
                {message}
              </p>
            )}
            {errorMessage && (
              <p
                role="alert"
                className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-bold text-red-900"
              >
                {errorMessage}
              </p>
            )}
          </div>
        )}

        {loading ? (
          <Notice>점검 작업지시를 불러오고 있습니다.</Notice>
        ) : orders.length === 0 ? (
          <Notice>
            {initialDroneId !== null || initialStatus !== null
              ? "선택한 조건에 해당하는 점검 작업지시가 없습니다."
              : "생성된 작업지시가 없습니다. 기체 신뢰도 화면에서 위험 평가를 준비한 뒤 상단 동기화 버튼을 실행하세요."}
          </Notice>
        ) : (
          <div className="mt-6 space-y-4">
            {orders.map((order) => (
              <article
                key={order.id}
                id={`maintenance-work-order-${order.id}`}
                aria-current={
                  order.id === initialWorkOrderId ? "true" : undefined
                }
                className={`rounded-2xl border bg-white p-5 shadow-sm ${
                  order.id === initialWorkOrderId
                    ? "border-cyan-500 ring-4 ring-cyan-100"
                    : "border-slate-200"
                }`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-lg font-black text-slate-950">
                        작업 #{order.id} · Drone #{order.droneId}
                      </h2>
                      <span
                        className={`rounded-full border px-2.5 py-1 text-xs font-black ${statusStyles[order.status]}`}
                      >
                        {statusLabels[order.status]}
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-slate-600">
                      Incident #{order.incidentId} · 품질 평가 #
                      {order.sourceAssessmentId ?? "-"}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      접수 {formatKoreanDateTime(order.openedAt)}
                      {order.assignee ? ` · 담당 ${order.assignee}` : ""}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void toggleEvidence(order)}
                      className="rounded-lg border border-cyan-300 bg-cyan-50 px-3 py-2 text-sm font-bold text-cyan-800"
                    >
                      {expandedId === order.id
                        ? "처리 이력 닫기"
                        : "처리 이력·비행 허가"}
                    </button>
                    <Link
                      href={`/incidents/${order.incidentId}/report`}
                      className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-700"
                    >
                      Incident 보고서
                    </Link>
                  </div>
                </div>

                {(order.finding || order.resolutionNote) && (
                  <div className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-700">
                    {order.finding && <p>점검 결과: {order.finding}</p>}
                    {order.resolutionNote && (
                      <p className="mt-1">조치: {order.resolutionNote}</p>
                    )}
                  </div>
                )}

                {expandedId === order.id && (
                  <WorkOrderEvidencePanel
                    order={order}
                    evidence={evidenceById[order.id] ?? null}
                    loading={evidenceLoadingId === order.id}
                    errorMessage={evidenceErrorById[order.id] ?? null}
                  />
                )}

                {(order.status === "OPEN" || order.status === "GROUNDED") && (
                  <div className="mt-4">
                    <button
                      type="button"
                      disabled={!canOperate || busyId !== null}
                      title={
                        canOperate
                          ? undefined
                          : (operateDeniedReason ?? undefined)
                      }
                      onClick={() =>
                        mutate(
                          order.id,
                          "start",
                          {
                            assignee: actor,
                            actor,
                            note:
                              order.status === "GROUNDED"
                                ? "수리 후 재점검 시작"
                                : "기체 점검 시작",
                          },
                          `작업 #${order.id}의 점검을 시작했습니다.`,
                        )
                      }
                      className="rounded-lg bg-sky-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
                    >
                      {busyId === order.id
                        ? "처리 중..."
                        : order.status === "GROUNDED"
                          ? "수리 후 재점검"
                          : "점검 시작"}
                    </button>
                  </div>
                )}

                {order.status === "IN_PROGRESS" && (
                  <form
                    onSubmit={(event) => complete(event, order.id)}
                    className="mt-4 grid gap-3 rounded-xl border border-sky-200 bg-sky-50 p-4 md:grid-cols-2"
                  >
                    <label className="text-sm font-bold text-slate-800">
                      점검 결과
                      <textarea
                        name="finding"
                        required
                        maxLength={1000}
                        rows={3}
                        placeholder="기체·배터리·통신·센서 점검 결과"
                        className="mt-1 block w-full rounded-lg border border-slate-300 bg-white p-3 font-normal"
                      />
                    </label>
                    <label className="text-sm font-bold text-slate-800">
                      조치 메모
                      <textarea
                        name="resolutionNote"
                        required
                        maxLength={1000}
                        rows={3}
                        placeholder="수리·교체·재시험 및 승인 근거"
                        className="mt-1 block w-full rounded-lg border border-slate-300 bg-white p-3 font-normal"
                      />
                    </label>
                    <label className="text-sm font-bold text-slate-800">
                      최종 판정
                      <select
                        name="decision"
                        defaultValue="RETURN_TO_SERVICE"
                        className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-normal"
                      >
                        <option value="RETURN_TO_SERVICE">재운항 승인</option>
                        <option value="KEEP_GROUNDED">운항 중지 유지</option>
                      </select>
                    </label>
                    <div className="flex items-end">
                      <button
                        type="submit"
                        disabled={!canOperate || busyId !== null}
                        className="w-full rounded-lg bg-slate-950 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
                      >
                        {busyId === order.id
                          ? "저장 중..."
                          : "점검 결과 저장"}
                      </button>
                    </div>
                  </form>
                )}
              </article>
            ))}
          </div>
        )}

        <p className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs leading-5 text-amber-900">
          비행 시작 게이트는 OFF·ADVISORY·ENFORCED 모드를 지원합니다.
          기본 ADVISORY는 경고만 표시해 발표 흐름을 보호하고, ENFORCED는
          재운항 승인 전 새 비행 세션 생성을 차단합니다.
        </p>
      </section>
    </main>
  );
}

function WorkOrderEvidencePanel({
  order,
  evidence,
  loading,
  errorMessage,
}: {
  order: MaintenanceWorkOrder;
  evidence: WorkOrderEvidence | null;
  loading: boolean;
  errorMessage: string | null;
}) {
  if (loading && !evidence) {
    return (
      <p className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
        점검 처리 이력과 현재 비행 허가를 확인하고 있습니다.
      </p>
    );
  }

  if (errorMessage && !evidence) {
    return (
      <p className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-bold text-red-800">
        {errorMessage}
      </p>
    );
  }

  if (!evidence) {
    return null;
  }

  const clearance = evidence.clearance;
  const clearanceLabel = !clearance
    ? "허가 조회 불가"
    : !clearance.flightAllowed
      ? "비행 차단"
      : clearance.attentionRequired
        ? "주의 후 허용"
        : "비행 가능";
  const clearanceStyle = !clearance
    ? "border-slate-200 bg-slate-50 text-slate-700"
    : !clearance.flightAllowed
      ? "border-red-200 bg-red-50 text-red-800"
      : clearance.attentionRequired
        ? "border-amber-200 bg-amber-50 text-amber-800"
        : "border-emerald-200 bg-emerald-50 text-emerald-800";
  const currentWorkOrder =
    clearance?.workOrderId === null || clearance?.workOrderId === order.id;

  return (
    <section className="mt-4 rounded-xl border border-cyan-200 bg-cyan-50/40 p-4">
      <div
        className={`flex flex-wrap items-start justify-between gap-3 rounded-xl border p-4 ${clearanceStyle}`}
      >
        <div>
          <p className="text-xs font-black uppercase tracking-wide">
            현재 비행 허가 검증
          </p>
          <p className="mt-1 text-lg font-black">{clearanceLabel}</p>
          <p className="mt-1 text-sm">
            {clearance?.reason ??
              "비행 허가 API 응답을 확인할 수 없습니다. 서버 상태를 점검하세요."}
          </p>
          {clearance && (
            <p className="mt-1 text-xs font-bold">
              {currentWorkOrder
                ? "현재 작업지시 결과가 비행 게이트에 반영되었습니다."
                : `더 최신 작업 #${clearance.workOrderId}가 비행 게이트를 결정하고 있습니다.`}
            </p>
          )}
        </div>
        <Link
          href={`/drones?droneId=${order.droneId}`}
          className="rounded-lg border border-current bg-white px-3 py-2 text-sm font-bold"
        >
          관제에서 재확인
        </Link>
      </div>

      <div className="mt-4">
        <h3 className="font-black text-slate-950">작업 처리 타임라인</h3>
        {evidence.detail.history.length === 0 ? (
          <p className="mt-3 text-sm text-slate-600">
            저장된 처리 이력이 없습니다.
          </p>
        ) : (
          <ol className="mt-3 space-y-3">
            {evidence.detail.history.map((history) => (
              <li
                key={history.id}
                className="relative border-l-2 border-cyan-300 pl-4"
              >
                <span className="absolute -left-[7px] top-1 h-3 w-3 rounded-full bg-cyan-600" />
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-black text-slate-900">
                    {actionLabels[history.actionType]}
                  </span>
                  <span className="text-xs font-bold text-slate-500">
                    {history.previousStatus
                      ? `${statusLabels[history.previousStatus]} → `
                      : ""}
                    {statusLabels[history.newStatus]}
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-700">
                  {history.note || "처리 메모 없음"}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {history.actor} · {formatKoreanDateTime(history.createdAt)}
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

function Counter({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-bold text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-black text-slate-950">{value}건</p>
    </div>
  );
}

function Notice({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
      {children}
    </p>
  );
}
