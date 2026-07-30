"use client";

import Image from "next/image";
import Link from "next/link";
import {
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";

import { useOperatorAccess } from "@/components/security/operator-access-provider";
import { formatKoreanDateTime } from "@/lib/date";
import {
    parseAiAlertDetail,
    parseAiAlertItem,
    parseAiAlertList,
    type AiAlertDetail,
    type AiAlertItem,
    type AiAlertQuery,
    type AiAlertSeverity,
    type AiAlertStatus,
} from "@/types/ai-alert";

interface AiAlertOperationsPanelProps {
    initialAlerts: AiAlertItem[];
    initialError: string | null;
    initialQuery: AiAlertQuery;
}

type SeverityFilter = "" | AiAlertSeverity;
type StatusFilter = "" | AiAlertStatus;
type AlertAction = "acknowledge" | "resolve";

const AUTO_REFRESH_INTERVAL_MS = 5_000;

function severityPresentation(severity: AiAlertSeverity) {
    return {
        INFO: {
            label: "경보",
            badgeClassName: "bg-sky-100 text-sky-800",
            cardClassName: "border-sky-200 bg-sky-50/40",
        },
        WARNING: {
            label: "주의",
            badgeClassName: "bg-amber-100 text-amber-900",
            cardClassName: "border-amber-300 bg-amber-50/50",
        },
        CRITICAL: {
            label: "긴급",
            badgeClassName: "bg-rose-100 text-rose-900",
            cardClassName: "border-rose-300 bg-rose-50/60",
        },
    }[severity];
}

function statusPresentation(status: AiAlertStatus) {
    return {
        OPEN: {
            label: "미확인",
            className: "bg-rose-100 text-rose-800",
        },
        ACKNOWLEDGED: {
            label: "확인",
            className: "bg-amber-100 text-amber-900",
        },
        RESOLVED: {
            label: "해결",
            className: "bg-emerald-100 text-emerald-800",
        },
    }[status];
}

function formatConfidence(value: number): string {
    return `${(Number(value) * 100).toFixed(1)}%`;
}

function formatBytes(value: number | null): string {
    if (value === null || !Number.isFinite(value)) {
        return "-";
    }

    if (value < 1024) {
        return `${value} B`;
    }

    if (value < 1024 * 1024) {
        return `${(value / 1024).toFixed(1)} KB`;
    }

    return `${(value / (1024 * 1024)).toFixed(2)} MB`;
}

function buildClientSearchParams(
    query: AiAlertQuery,
    severity: SeverityFilter,
    status: StatusFilter,
): URLSearchParams {
    const searchParams = new URLSearchParams({
        limit: String(query.limit ?? 50),
    });

    if (query.droneId !== undefined) {
        searchParams.set("droneId", String(query.droneId));
    }

    if (query.sessionId) {
        searchParams.set("sessionId", query.sessionId);
    }

    if (query.from) {
        searchParams.set("from", query.from);
    }

    if (query.to) {
        searchParams.set("to", query.to);
    }

    if (severity) {
        searchParams.set("severity", severity);
    }

    if (status) {
        searchParams.set("status", status);
    }

    return searchParams;
}

function extractErrorMessage(body: unknown, fallback: string): string {
    if (
        typeof body === "object" &&
        body !== null &&
        "message" in body &&
        typeof body.message === "string"
    ) {
        return body.message;
    }

    return fallback;
}

async function fetchJson(
    input: RequestInfo | URL,
    init?: RequestInit,
): Promise<unknown> {
    const headers = new Headers(init?.headers);
    headers.set("Accept", "application/json");

    const response = await fetch(input, {
        ...init,
        cache: "no-store",
        headers,
    });

    let body: unknown = null;

    try {
        body = await response.json();
    } catch {
        // 오류 응답에 JSON 본문이 없을 수 있습니다.
    }

    if (!response.ok) {
        throw new Error(
            extractErrorMessage(
                body,
                `AI 경보 요청 실패: HTTP ${response.status}`,
            ),
        );
    }

    return body;
}

export function AiAlertOperationsPanel({
    initialAlerts,
    initialError,
    initialQuery,
}: AiAlertOperationsPanelProps) {
    const { canOperate, operateDeniedReason } = useOperatorAccess();
    const [alerts, setAlerts] = useState(initialAlerts);
    const [listError, setListError] = useState(initialError);
    const [severityFilter, setSeverityFilter] =
        useState<SeverityFilter>("");
    const [statusFilter, setStatusFilter] = useState<StatusFilter>("");
    const [autoRefresh, setAutoRefresh] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [selectedAlertId, setSelectedAlertId] = useState<number | null>(null);
    const [detail, setDetail] = useState<AiAlertDetail | null>(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailError, setDetailError] = useState<string | null>(null);
    const [operator, setOperator] = useState("visionflow-operator");
    const [resolutionNote, setResolutionNote] = useState("");
    const [busyAction, setBusyAction] = useState<AlertAction | null>(null);
    const [actionMessage, setActionMessage] = useState<string | null>(null);
    const [actionError, setActionError] = useState<string | null>(null);
    const didMountFilters = useRef(false);

    const counts = useMemo(
        () => ({
            open: alerts.filter((alert) => alert.status === "OPEN").length,
            critical: alerts.filter(
                (alert) => alert.severity === "CRITICAL",
            ).length,
            warning: alerts.filter(
                (alert) => alert.severity === "WARNING",
            ).length,
        }),
        [alerts],
    );

    const refreshAlerts = useCallback(
        async (silent = false) => {
            if (!silent) {
                setRefreshing(true);
            }

            try {
                const searchParams = buildClientSearchParams(
                    initialQuery,
                    severityFilter,
                    statusFilter,
                );
                const body = await fetchJson(
                    `/api/ai/alerts?${searchParams.toString()}`,
                );
                const nextAlerts = parseAiAlertList(body);

                if (!nextAlerts) {
                    throw new Error("AI 경보 목록 응답 형식이 올바르지 않습니다.");
                }

                setAlerts(nextAlerts);
                setListError(null);
            } catch (error) {
                setListError(
                    error instanceof Error
                        ? error.message
                        : "AI 경보 목록을 갱신하지 못했습니다.",
                );
            } finally {
                if (!silent) {
                    setRefreshing(false);
                }
            }
        },
        [initialQuery, severityFilter, statusFilter],
    );

    useEffect(() => {
        if (!didMountFilters.current) {
            didMountFilters.current = true;
            return;
        }

        void refreshAlerts();
    }, [refreshAlerts]);

    useEffect(() => {
        if (!autoRefresh) {
            return;
        }

        const intervalId = window.setInterval(() => {
            if (document.visibilityState === "visible") {
                void refreshAlerts(true);
            }
        }, AUTO_REFRESH_INTERVAL_MS);

        return () => window.clearInterval(intervalId);
    }, [autoRefresh, refreshAlerts]);

    useEffect(() => {
        if (selectedAlertId === null) {
            return;
        }

        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === "Escape" && busyAction === null) {
                setSelectedAlertId(null);
                setDetail(null);
            }
        }

        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
    }, [busyAction, selectedAlertId]);

    async function openDetail(alertId: number) {
        setSelectedAlertId(alertId);
        setDetail(null);
        setDetailError(null);
        setActionError(null);
        setActionMessage(null);
        setResolutionNote("");
        setDetailLoading(true);

        try {
            const body = await fetchJson(`/api/ai/alerts/${alertId}`);
            const nextDetail = parseAiAlertDetail(body);

            if (!nextDetail) {
                throw new Error("AI 경보 상세 응답 형식이 올바르지 않습니다.");
            }

            setDetail(nextDetail);
        } catch (error) {
            setDetailError(
                error instanceof Error
                    ? error.message
                    : "AI 경보 상세를 불러오지 못했습니다.",
            );
        } finally {
            setDetailLoading(false);
        }
    }

    function closeDetail() {
        if (busyAction !== null) {
            return;
        }

        setSelectedAlertId(null);
        setDetail(null);
        setDetailError(null);
        setActionError(null);
        setActionMessage(null);
    }

    async function runAlertAction(action: AlertAction) {
        if (!detail || busyAction !== null) {
            return;
        }

        if (!canOperate) {
            setActionError(operateDeniedReason);
            return;
        }

        const normalizedOperator = operator.trim();

        if (!normalizedOperator) {
            setActionError("처리자 이름을 입력하세요.");
            return;
        }

        setBusyAction(action);
        setActionError(null);
        setActionMessage(null);

        try {
            const body = await fetchJson(
                `/api/ai/alerts/${detail.alert.id}/${action}`,
                {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(
                        action === "acknowledge"
                            ? { operator: normalizedOperator }
                            : {
                                  operator: normalizedOperator,
                                  note: resolutionNote.trim() || null,
                              },
                    ),
                },
            );
            const updatedAlert = parseAiAlertItem(body);

            if (!updatedAlert) {
                throw new Error("AI 경보 처리 응답 형식이 올바르지 않습니다.");
            }

            setAlerts((current) =>
                current.map((alert) =>
                    alert.id === updatedAlert.id ? updatedAlert : alert,
                ),
            );
            setDetail((current) =>
                current
                    ? {
                          ...current,
                          alert: updatedAlert,
                      }
                    : current,
            );
            setActionMessage(
                action === "acknowledge"
                    ? "경보를 확인 상태로 변경했습니다."
                    : "경보를 해결 상태로 변경했습니다.",
            );
        } catch (error) {
            setActionError(
                error instanceof Error
                    ? error.message
                    : "AI 경보 상태를 변경하지 못했습니다.",
            );
        } finally {
            setBusyAction(null);
        }
    }

    return (
        <section
            id="ai-alert-operations"
            aria-labelledby="ai-alert-operations-title"
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
        >
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <p className="text-sm font-semibold uppercase tracking-wider text-rose-700">
                        AI Safety Alerts
                    </p>
                    <h2
                        id="ai-alert-operations-title"
                        className="mt-1 text-xl font-bold text-slate-950"
                    >
                        AI 탐지 경보 관제
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">
                        위험도와 처리 상태를 확인하고 관제 조치를 기록합니다.
                    </p>
                </div>

                <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
                    <span className="rounded-full bg-rose-100 px-3 py-1.5 text-rose-800">
                        미확인 {counts.open}건
                    </span>
                    <span className="rounded-full bg-red-100 px-3 py-1.5 text-red-900">
                        긴급 {counts.critical}건
                    </span>
                    <span className="rounded-full bg-amber-100 px-3 py-1.5 text-amber-900">
                        주의 {counts.warning}건
                    </span>
                </div>
            </div>

            <div className="mt-4 flex flex-wrap items-end gap-3 rounded-xl bg-slate-50 p-4">
                <label className="text-sm font-semibold text-slate-700">
                    위험도
                    <select
                        value={severityFilter}
                        onChange={(event) =>
                            setSeverityFilter(
                                event.target.value as SeverityFilter,
                            )
                        }
                        className="mt-1 block rounded-lg border border-slate-300 bg-white px-3 py-2 font-normal text-slate-900"
                    >
                        <option value="">전체 위험도</option>
                        <option value="CRITICAL">긴급</option>
                        <option value="WARNING">주의</option>
                        <option value="INFO">경보</option>
                    </select>
                </label>

                <label className="text-sm font-semibold text-slate-700">
                    처리 상태
                    <select
                        value={statusFilter}
                        onChange={(event) =>
                            setStatusFilter(event.target.value as StatusFilter)
                        }
                        className="mt-1 block rounded-lg border border-slate-300 bg-white px-3 py-2 font-normal text-slate-900"
                    >
                        <option value="">전체 상태</option>
                        <option value="OPEN">미확인</option>
                        <option value="ACKNOWLEDGED">확인</option>
                        <option value="RESOLVED">해결</option>
                    </select>
                </label>

                <label className="flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-700">
                    <input
                        type="checkbox"
                        checked={autoRefresh}
                        onChange={(event) => setAutoRefresh(event.target.checked)}
                    />
                    5초 자동 갱신
                </label>

                <button
                    type="button"
                    onClick={() => void refreshAlerts()}
                    disabled={refreshing}
                    className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-bold text-white hover:bg-slate-700 disabled:cursor-wait disabled:opacity-60"
                >
                    {refreshing ? "갱신 중" : "지금 새로고침"}
                </button>

                <div className="ml-auto text-right text-xs text-slate-500">
                    {initialQuery.droneId
                        ? `대시보드 필터: 드론 #${initialQuery.droneId}`
                        : "대시보드 필터: 전체 드론"}
                    <div>현재 조회 결과 {alerts.length}건</div>
                </div>
            </div>

            {listError && (
                <div className="mt-4 rounded-xl border border-red-300 bg-red-50 px-4 py-3 text-sm font-medium text-red-800">
                    AI 경보를 불러오지 못했습니다: {listError}
                </div>
            )}

            {alerts.length === 0 ? (
                <div className="mt-4 rounded-xl bg-slate-50 p-6 text-center text-sm text-slate-500">
                    선택한 조건에 해당하는 AI 경보가 없습니다.
                </div>
            ) : (
                <div className="mt-4 grid gap-3 xl:grid-cols-2">
                    {alerts.map((alert) => {
                        const severity = severityPresentation(alert.severity);
                        const status = statusPresentation(alert.status);

                        return (
                            <article
                                key={alert.id}
                                className={`rounded-xl border p-4 ${severity.cardClassName}`}
                            >
                                <div className="flex items-start justify-between gap-3">
                                    <div className="min-w-0">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <span
                                                className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${severity.badgeClassName}`}
                                            >
                                                {severity.label}
                                            </span>
                                            <span
                                                className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${status.className}`}
                                            >
                                                {status.label}
                                            </span>
                                            {alert.snapshotAvailable && (
                                                <span className="rounded-full bg-violet-100 px-2.5 py-1 text-[11px] font-bold text-violet-800">
                                                    스냅샷
                                                </span>
                                            )}
                                        </div>
                                        <h3 className="mt-2 break-words font-bold text-slate-950">
                                            {alert.title}
                                        </h3>
                                        <p className="mt-1 text-sm text-slate-600">
                                            {alert.summary}
                                        </p>
                                    </div>

                                    <div className="shrink-0 text-right">
                                        <div className="text-lg font-bold text-slate-950">
                                            {formatConfidence(alert.maxConfidence)}
                                        </div>
                                        <div className="text-[11px] text-slate-500">
                                            {alert.primaryClassName}
                                        </div>
                                    </div>
                                </div>

                                <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
                                    <span>경보 #{alert.id}</span>
                                    <span>드론 #{alert.droneId}</span>
                                    <span>탐지 {alert.detectionCount}개</span>
                                    <span>{formatKoreanDateTime(alert.capturedAt)}</span>
                                </div>

                                <div className="mt-2 break-all font-mono text-[11px] text-slate-500">
                                    {alert.sessionId}
                                </div>

                                <div className="mt-3 flex flex-wrap justify-end gap-2 border-t border-slate-200/80 pt-3">
                                    <Link
                                        href={`/drones?droneId=${alert.droneId}&sessionId=${encodeURIComponent(alert.sessionId)}#flight-session-replay`}
                                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-bold text-slate-700 hover:border-slate-400"
                                    >
                                        비행 경로
                                    </Link>
                                    <button
                                        type="button"
                                        onClick={() => void openDetail(alert.id)}
                                        className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white hover:bg-slate-700"
                                    >
                                        상세 및 조치
                                    </button>
                                </div>
                            </article>
                        );
                    })}
                </div>
            )}

            {selectedAlertId !== null && (
                <div
                    className="fixed inset-0 z-50 overflow-y-auto bg-slate-950/70 p-4 sm:p-8"
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="ai-alert-detail-title"
                >
                    <div className="mx-auto max-w-5xl rounded-2xl bg-white shadow-2xl">
                        <div className="flex items-start justify-between gap-4 border-b border-slate-200 p-5">
                            <div>
                                <h3
                                    id="ai-alert-detail-title"
                                    className="text-xl font-bold text-slate-950"
                                >
                                    AI 경보 상세 및 관제 조치
                                </h3>
                                <p className="mt-1 text-sm text-slate-500">
                                    경보 #{selectedAlertId}
                                </p>
                            </div>
                            <button
                                type="button"
                                onClick={closeDetail}
                                disabled={busyAction !== null}
                                aria-label="경보 상세 닫기"
                                className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-700 disabled:opacity-40"
                            >
                                닫기
                            </button>
                        </div>

                        <div className="p-5">
                            {detailLoading && (
                                <div className="rounded-xl bg-slate-50 p-8 text-center text-sm text-slate-500">
                                    경보 상세를 불러오는 중입니다.
                                </div>
                            )}

                            {detailError && (
                                <div className="rounded-xl border border-red-300 bg-red-50 p-4 text-sm font-medium text-red-800">
                                    {detailError}
                                </div>
                            )}

                            {detail && (
                                <AlertDetailContent
                                    detail={detail}
                                    operator={operator}
                                    resolutionNote={resolutionNote}
                                    busyAction={busyAction}
                                    actionMessage={actionMessage}
                                    actionError={actionError}
                                    canOperate={canOperate}
                                    operateDeniedReason={operateDeniedReason}
                                    onOperatorChange={setOperator}
                                    onResolutionNoteChange={setResolutionNote}
                                    onAction={runAlertAction}
                                />
                            )}
                        </div>
                    </div>
                </div>
            )}
        </section>
    );
}

function AlertDetailContent({
    detail,
    operator,
    resolutionNote,
    busyAction,
    actionMessage,
    actionError,
    canOperate,
    operateDeniedReason,
    onOperatorChange,
    onResolutionNoteChange,
    onAction,
}: {
    detail: AiAlertDetail;
    operator: string;
    resolutionNote: string;
    busyAction: AlertAction | null;
    actionMessage: string | null;
    actionError: string | null;
    canOperate: boolean;
    operateDeniedReason: string | null;
    onOperatorChange: (value: string) => void;
    onResolutionNoteChange: (value: string) => void;
    onAction: (action: AlertAction) => Promise<void>;
}) {
    const severity = severityPresentation(detail.alert.severity);
    const status = statusPresentation(detail.alert.status);
    const snapshotUrl = detail.alert.snapshotUrl ?? detail.event.snapshotUrl;

    return (
        <div className="space-y-5">
            <div className="grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
                <div>
                    {detail.alert.snapshotAvailable && snapshotUrl ? (
                        <div className="overflow-hidden rounded-xl border border-slate-200 bg-slate-950">
                            <Image
                                src={snapshotUrl}
                                alt={`${detail.alert.title} 분석 스냅샷`}
                                width={1280}
                                height={720}
                                unoptimized
                                className="h-auto w-full object-contain"
                            />
                        </div>
                    ) : (
                        <div className="flex min-h-64 items-center justify-center rounded-xl bg-slate-100 p-6 text-center text-sm text-slate-500">
                            이 경보에는 저장된 분석 스냅샷이 없습니다.
                        </div>
                    )}

                    <div className="mt-2 text-xs text-slate-500">
                        스냅샷 크기 {formatBytes(detail.event.snapshotSizeBytes)}
                    </div>
                </div>

                <div className="rounded-xl border border-slate-200 p-4">
                    <div className="flex flex-wrap gap-2">
                        <span
                            className={`rounded-full px-2.5 py-1 text-xs font-bold ${severity.badgeClassName}`}
                        >
                            {severity.label}
                        </span>
                        <span
                            className={`rounded-full px-2.5 py-1 text-xs font-bold ${status.className}`}
                        >
                            {status.label}
                        </span>
                    </div>

                    <h4 className="mt-3 text-lg font-bold text-slate-950">
                        {detail.alert.title}
                    </h4>
                    <p className="mt-1 text-sm text-slate-600">
                        {detail.alert.summary}
                    </p>

                    <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
                        <DetailValue label="드론" value={`#${detail.alert.droneId}`} />
                        <DetailValue
                            label="최고 신뢰도"
                            value={formatConfidence(detail.alert.maxConfidence)}
                        />
                        <DetailValue
                            label="대표 객체"
                            value={detail.alert.primaryClassName}
                        />
                        <DetailValue
                            label="추론 시간"
                            value={`${Number(detail.event.inferenceMs).toFixed(2)}ms`}
                        />
                        <DetailValue
                            label="프레임"
                            value={`#${detail.event.frameIndex}`}
                        />
                        <DetailValue
                            label="영상 소스"
                            value={detail.event.sourceType}
                        />
                    </dl>

                    <div className="mt-4 border-t border-slate-200 pt-3 text-xs text-slate-500">
                        <div>{formatKoreanDateTime(detail.alert.capturedAt)}</div>
                        <div className="mt-1 break-all font-mono">
                            {detail.alert.sessionId}
                        </div>
                    </div>

                    <Link
                        href={`/drones?droneId=${detail.alert.droneId}&sessionId=${encodeURIComponent(detail.alert.sessionId)}#flight-session-replay`}
                        className="mt-4 inline-flex rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white hover:bg-slate-700"
                    >
                        해당 비행 경로 재생
                    </Link>
                </div>
            </div>

            <div className="rounded-xl border border-slate-200 p-4">
                <h4 className="font-bold text-slate-950">
                    탐지 객체 {detail.event.detections.length}개
                </h4>
                <div className="mt-3 grid gap-2 md:grid-cols-2">
                    {detail.event.detections.map((detection) => (
                        <div
                            key={detection.id}
                            className="rounded-lg bg-slate-50 px-3 py-2 text-sm"
                        >
                            <div className="flex items-center justify-between gap-3">
                                <span className="font-bold text-slate-900">
                                    {detection.className}
                                </span>
                                <span className="font-bold text-violet-700">
                                    {formatConfidence(detection.confidence)}
                                </span>
                            </div>
                            <div className="mt-1 text-xs text-slate-500">
                                bbox [{Number(detection.x1).toFixed(1)}, {Number(detection.y1).toFixed(1)}]
                                {" → "}
                                [{Number(detection.x2).toFixed(1)}, {Number(detection.y2).toFixed(1)}]
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            <div className="rounded-xl border border-cyan-200 bg-cyan-50/40 p-4">
                <h4 className="font-bold text-slate-950">관제 조치</h4>

                {!canOperate && operateDeniedReason && (
                    <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-900">
                        {operateDeniedReason}
                    </div>
                )}

                {detail.alert.acknowledgedAt && (
                    <p className="mt-2 text-xs text-slate-600">
                        확인: {detail.alert.acknowledgedBy} · {formatKoreanDateTime(detail.alert.acknowledgedAt)}
                    </p>
                )}

                {detail.alert.resolvedAt && (
                    <div className="mt-2 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900">
                        <div className="font-bold">
                            해결: {detail.alert.resolvedBy} · {formatKoreanDateTime(detail.alert.resolvedAt)}
                        </div>
                        {detail.alert.resolutionNote && (
                            <div className="mt-1">{detail.alert.resolutionNote}</div>
                        )}
                    </div>
                )}

                {detail.alert.status !== "RESOLVED" && (
                    <div className="mt-4 grid gap-3 lg:grid-cols-2">
                        <label className="text-sm font-semibold text-slate-700">
                            처리자
                            <input
                                type="text"
                                value={operator}
                                onChange={(event) =>
                                    onOperatorChange(event.target.value)
                                }
                                maxLength={100}
                                disabled={busyAction !== null || !canOperate}
                                className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-normal text-slate-900 disabled:opacity-60"
                            />
                        </label>

                        <label className="text-sm font-semibold text-slate-700">
                            해결 메모
                            <textarea
                                value={resolutionNote}
                                onChange={(event) =>
                                    onResolutionNoteChange(event.target.value)
                                }
                                maxLength={500}
                                rows={2}
                                disabled={busyAction !== null || !canOperate}
                                placeholder="현장 확인 결과 또는 조치 내용을 입력하세요."
                                className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-normal text-slate-900 disabled:opacity-60"
                            />
                        </label>
                    </div>
                )}

                {actionError && (
                    <div className="mt-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm font-medium text-red-800">
                        {actionError}
                    </div>
                )}

                {actionMessage && (
                    <div className="mt-3 rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-800">
                        {actionMessage}
                    </div>
                )}

                {detail.alert.status !== "RESOLVED" && (
                    <div className="mt-4 flex flex-wrap justify-end gap-2">
                        {detail.alert.status === "OPEN" && (
                            <button
                                type="button"
                                onClick={() => void onAction("acknowledge")}
                                disabled={busyAction !== null || !canOperate}
                                title={canOperate ? undefined : operateDeniedReason ?? undefined}
                                className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-bold text-white hover:bg-amber-500 disabled:cursor-wait disabled:opacity-60"
                            >
                                {busyAction === "acknowledge"
                                    ? "확인 처리 중"
                                    : "경보 확인"}
                            </button>
                        )}
                        <button
                            type="button"
                            onClick={() => void onAction("resolve")}
                            disabled={busyAction !== null || !canOperate}
                            title={canOperate ? undefined : operateDeniedReason ?? undefined}
                            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-bold text-white hover:bg-emerald-600 disabled:cursor-wait disabled:opacity-60"
                        >
                            {busyAction === "resolve"
                                ? "해결 처리 중"
                                : "경보 해결"}
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}

function DetailValue({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-lg bg-slate-50 p-3">
            <dt className="text-xs font-semibold text-slate-500">{label}</dt>
            <dd className="mt-1 break-words font-bold text-slate-900">
                {value}
            </dd>
        </div>
    );
}
