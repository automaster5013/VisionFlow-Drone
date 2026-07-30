"use client";

import Link from "next/link";
import {
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";

import { useOperatorAccess } from "@/components/security/operator-access-provider";
import { useIncidentRealtime } from "@/hooks/use-incident-realtime";
import { formatKoreanDateTime } from "@/lib/date";
import {
    parseIncidentDetail,
    parseIncidentList,
    type IncidentDetail,
    type IncidentItem,
    type IncidentPriority,
    type IncidentQuery,
    type IncidentSourceType,
    type IncidentStatus,
} from "@/types/incident";
import type { IncidentRealtimeConnectionStatus } from "@/types/incident-realtime";

interface IncidentOperationsPanelProps {
    initialIncidents: IncidentItem[];
    initialError: string | null;
    initialQuery: IncidentQuery;
}

type SourceFilter = "" | IncidentSourceType;
type PriorityFilter = "" | IncidentPriority;
type StatusFilter = "" | IncidentStatus;
type BusyAction = "ASSIGNEE" | "PRIORITY" | "STATUS" | "NOTE";

const FALLBACK_REFRESH_INTERVAL_MS = 15_000;

const PRIORITIES: IncidentPriority[] = [
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
];

function priorityPresentation(priority: IncidentPriority) {
    return {
        LOW: { label: "낮음", className: "bg-sky-100 text-sky-800" },
        MEDIUM: { label: "보통", className: "bg-indigo-100 text-indigo-800" },
        HIGH: { label: "높음", className: "bg-amber-100 text-amber-900" },
        CRITICAL: { label: "긴급", className: "bg-rose-100 text-rose-900" },
    }[priority];
}

function statusPresentation(status: IncidentStatus) {
    return {
        OPEN: { label: "미처리", className: "bg-rose-100 text-rose-800" },
        IN_PROGRESS: {
            label: "처리 중",
            className: "bg-amber-100 text-amber-900",
        },
        RESOLVED: {
            label: "해결",
            className: "bg-emerald-100 text-emerald-800",
        },
        CLOSED: { label: "종료", className: "bg-slate-200 text-slate-700" },
    }[status];
}

function sourceLabel(sourceType: IncidentSourceType): string {
    return {
        AI_ALERT: "AI 경보",
        GEOFENCE: "지오펜스",
        FLIGHT_QUALITY: "기체 신뢰도",
        FLIGHT_GATE: "비행 시작 차단",
    }[sourceType];
}

function formatSlaRemaining(remainingMs: number): string {
    const totalSeconds = Math.max(0, Math.ceil(remainingMs / 1_000));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;

    return minutes > 0 ? `${minutes}분 ${seconds}초` : `${seconds}초`;
}

function slaPresentation(incident: IncidentItem, nowMs: number) {
    if (incident.slaBreachedAt) {
        return {
            label: `SLA 초과 · Lv.${incident.escalationLevel}`,
            className: "bg-red-600 text-white",
        };
    }

    if (incident.status === "RESOLVED" || incident.status === "CLOSED") {
        return {
            label: "SLA 준수",
            className: "bg-emerald-100 text-emerald-800",
        };
    }

    if (!incident.slaDueAt) {
        return {
            label: "SLA 없음",
            className: "bg-slate-100 text-slate-600",
        };
    }

    const dueAt = Date.parse(incident.slaDueAt);
    if (!Number.isFinite(dueAt)) {
        return {
            label: "SLA 시각 오류",
            className: "bg-slate-100 text-slate-600",
        };
    }

    const remainingMs = dueAt - nowMs;
    if (remainingMs <= 0) {
        return {
            label: "SLA 초과 감지 중",
            className: "bg-red-100 text-red-900",
        };
    }

    return {
        label: `SLA ${formatSlaRemaining(remainingMs)} 남음`,
        className:
            remainingMs <= 5 * 60 * 1_000
                ? "bg-orange-100 text-orange-900"
                : "bg-cyan-100 text-cyan-900",
    };
}

function locationSourceLabel(source: IncidentDetail["context"]["locationSource"]): string {
    return {
        GEOFENCE_EVENT: "지오펜스 이벤트 좌표",
        NEAREST_TELEMETRY: "발생 시각 인접 텔레메트리",
        UNAVAILABLE: "좌표 없음",
    }[source];
}

function buildIncidentNavigationHref(detail: IncidentDetail): string {
    const { incident, context } = detail;
    const params = new URLSearchParams({
        droneId: String(context.droneId),
        incidentId: String(incident.id),
        incidentAt: context.occurredAt,
        incidentSource: incident.sourceType,
    });

    if (context.replayAvailable && context.sessionId) {
        params.set("sessionId", context.sessionId);
    }
    if (context.latitude !== null) {
        params.set("incidentLat", String(context.latitude));
    }
    if (context.longitude !== null) {
        params.set("incidentLng", String(context.longitude));
    }
    if (context.altitude !== null) {
        params.set("incidentAlt", String(context.altitude));
    }

    return `/drones?${params.toString()}`;
}

function allowedNextStatuses(status: IncidentStatus): IncidentStatus[] {
    return {
        OPEN: ["IN_PROGRESS", "RESOLVED"],
        IN_PROGRESS: ["OPEN", "RESOLVED"],
        RESOLVED: ["IN_PROGRESS", "CLOSED"],
        CLOSED: [],
    }[status] as IncidentStatus[];
}

function buildSearchParams(
    query: IncidentQuery,
    sourceType: SourceFilter,
    priority: PriorityFilter,
    status: StatusFilter,
    assignee: string,
): URLSearchParams {
    const params = new URLSearchParams({
        limit: String(query.limit ?? 100),
    });

    if (query.droneId !== undefined) {
        params.set("droneId", String(query.droneId));
    }
    if (query.from) params.set("from", query.from);
    if (query.to) params.set("to", query.to);
    if (sourceType) params.set("sourceType", sourceType);
    if (priority) params.set("priority", priority);
    if (status) params.set("status", status);
    if (assignee.trim()) params.set("assignee", assignee.trim());

    return params;
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
        // 오류 응답이 JSON이 아니면 HTTP 상태를 사용합니다.
    }

    if (!response.ok) {
        throw new Error(
            extractErrorMessage(
                body,
                `Incident 요청 실패: HTTP ${response.status}`,
            ),
        );
    }

    return body;
}

function connectionPresentation(status: IncidentRealtimeConnectionStatus) {
    return {
        CONNECTING: { label: "연결 중", className: "bg-slate-100 text-slate-700" },
        CONNECTED: { label: "실시간 연결", className: "bg-emerald-100 text-emerald-800" },
        DISCONNECTED: { label: "재연결 대기", className: "bg-amber-100 text-amber-900" },
        ERROR: { label: "연결 오류", className: "bg-rose-100 text-rose-800" },
    }[status] ?? { label: status, className: "bg-slate-100 text-slate-700" };
}

export function IncidentOperationsPanel({
    initialIncidents,
    initialError,
    initialQuery,
}: IncidentOperationsPanelProps) {
    const { canOperate, operateDeniedReason } = useOperatorAccess();
    const [incidents, setIncidents] = useState(initialIncidents);
    const [listError, setListError] = useState(initialError);
    const [sourceFilter, setSourceFilter] = useState<SourceFilter>("");
    const [priorityFilter, setPriorityFilter] = useState<PriorityFilter>("");
    const [statusFilter, setStatusFilter] = useState<StatusFilter>("");
    const [assigneeFilter, setAssigneeFilter] = useState("");
    const [autoRefresh, setAutoRefresh] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [selectedIncidentId, setSelectedIncidentId] = useState<number | null>(
        null,
    );
    const [detail, setDetail] = useState<IncidentDetail | null>(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailError, setDetailError] = useState<string | null>(null);
    const [operator, setOperator] = useState("visionflow-operator");
    const [assignee, setAssignee] = useState("");
    const [priority, setPriority] = useState<IncidentPriority>("MEDIUM");
    const [nextStatus, setNextStatus] = useState<IncidentStatus>("IN_PROGRESS");
    const [actionNote, setActionNote] = useState("");
    const [journalNote, setJournalNote] = useState("");
    const [busyAction, setBusyAction] = useState<BusyAction | null>(null);
    const [actionMessage, setActionMessage] = useState<string | null>(null);
    const [actionError, setActionError] = useState<string | null>(null);
    const [nowMs, setNowMs] = useState(() => Date.now());
    const didMountFilters = useRef(false);

    const counts = useMemo(
        () => ({
            open: incidents.filter((item) => item.status === "OPEN").length,
            inProgress: incidents.filter(
                (item) => item.status === "IN_PROGRESS",
            ).length,
            critical: incidents.filter(
                (item) => item.priority === "CRITICAL",
            ).length,
            unassigned: incidents.filter((item) => !item.assignee).length,
            slaBreached: incidents.filter((item) => item.slaBreachedAt !== null)
                .length,
        }),
        [incidents],
    );

    useEffect(() => {
        const timer = window.setInterval(() => {
            setNowMs(Date.now());
        }, 1_000);

        return () => window.clearInterval(timer);
    }, []);

    const refreshIncidents = useCallback(
        async (silent = false) => {
            if (!silent) setRefreshing(true);

            try {
                const params = buildSearchParams(
                    initialQuery,
                    sourceFilter,
                    priorityFilter,
                    statusFilter,
                    assigneeFilter,
                );
                const body = await fetchJson(`/api/incidents?${params}`);
                const parsed = parseIncidentList(body);

                if (!parsed) {
                    throw new Error("Incident 목록 응답 형식이 올바르지 않습니다.");
                }

                setIncidents(parsed);
                setListError(null);
            } catch (error) {
                setListError(
                    error instanceof Error
                        ? error.message
                        : "Incident 목록을 불러오지 못했습니다.",
                );
            } finally {
                if (!silent) setRefreshing(false);
            }
        },
        [
            assigneeFilter,
            initialQuery,
            priorityFilter,
            sourceFilter,
            statusFilter,
        ],
    );

    const loadDetail = useCallback(
        async (incidentId: number, resetForm: boolean) => {
            setDetailLoading(true);
            setDetailError(null);

            try {
                const body = await fetchJson(`/api/incidents/${incidentId}`);
                const parsed = parseIncidentDetail(body);

                if (!parsed) {
                    throw new Error("Incident 상세 응답 형식이 올바르지 않습니다.");
                }

                setDetail(parsed);

                if (resetForm) {
                    setAssignee(parsed.incident.assignee ?? "");
                    setPriority(parsed.incident.priority);
                    setNextStatus(
                        allowedNextStatuses(parsed.incident.status)[0] ??
                            parsed.incident.status,
                    );
                    setActionNote("");
                    setJournalNote("");
                }
            } catch (error) {
                setDetailError(
                    error instanceof Error
                        ? error.message
                        : "Incident 상세를 불러오지 못했습니다.",
                );
            } finally {
                setDetailLoading(false);
            }
        },
        [],
    );

    const handleRealtimeMessage = useCallback(() => {
        void refreshIncidents(true);

        if (selectedIncidentId !== null) {
            void loadDetail(selectedIncidentId, false);
        }
    }, [loadDetail, refreshIncidents, selectedIncidentId]);

    const { connectionStatus, lastMessageAt } = useIncidentRealtime(
        handleRealtimeMessage,
    );

    useEffect(() => {
        if (!didMountFilters.current) {
            didMountFilters.current = true;
            return;
        }

        const timer = window.setTimeout(() => {
            void refreshIncidents();
        }, 250);

        return () => window.clearTimeout(timer);
    }, [refreshIncidents]);

    useEffect(() => {
        if (!autoRefresh) return;

        const timer = window.setInterval(() => {
            void refreshIncidents(true);
        }, FALLBACK_REFRESH_INTERVAL_MS);

        return () => window.clearInterval(timer);
    }, [autoRefresh, refreshIncidents]);

    function openDetail(incidentId: number) {
        setSelectedIncidentId(incidentId);
        setDetail(null);
        setActionMessage(null);
        setActionError(null);
        void loadDetail(incidentId, true);
    }

    function closeDetail() {
        if (busyAction) return;
        setSelectedIncidentId(null);
        setDetail(null);
        setDetailError(null);
    }

    async function submitAction(
        action: BusyAction,
        path: string,
        method: "PATCH" | "POST",
        payload: Record<string, string>,
        successMessage: string,
    ) {
        if (selectedIncidentId === null) return;

        if (!canOperate) {
            setActionError(operateDeniedReason);
            return;
        }

        setBusyAction(action);
        setActionMessage(null);
        setActionError(null);

        try {
            await fetchJson(`/api/incidents/${selectedIncidentId}/${path}`, {
                method,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            setActionMessage(successMessage);
            await Promise.all([
                refreshIncidents(true),
                loadDetail(selectedIncidentId, true),
            ]);
        } catch (error) {
            setActionError(
                error instanceof Error
                    ? error.message
                    : "Incident 조치 요청에 실패했습니다.",
            );
        } finally {
            setBusyAction(null);
        }
    }

    const connection = connectionPresentation(connectionStatus);
    const selected = detail?.incident ?? null;
    const availableStatuses = selected
        ? allowedNextStatuses(selected.status)
        : [];

    return (
        <section aria-labelledby="incident-operations-title">
            <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                    <p className="text-sm font-semibold uppercase tracking-wider text-rose-700">
                        Unified Incident Operations
                    </p>
                    <h2
                        id="incident-operations-title"
                        className="mt-2 text-2xl font-bold tracking-tight text-slate-950"
                    >
                        통합 Incident 관제
                    </h2>
                    <p className="mt-2 text-sm leading-6 text-slate-600">
                        AI 경보·지오펜스 위반·기체 신뢰도·반복 비행 차단을 담당자·우선순위·처리 이력으로 통합 관리합니다.
                    </p>
                </div>

                <div className="flex items-center gap-3">
                    <Link
                        href="/demo-scenario"
                        className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-bold text-white hover:bg-slate-800"
                    >
                        발표 시연 콘솔
                    </Link>
                    <div className="text-right text-xs text-slate-500">
                        <span
                            className={`inline-flex rounded-full px-3 py-1 font-bold ${connection.className}`}
                        >
                            {connection.label}
                        </span>
                        <div className="mt-1">
                            마지막 실시간 수신 {lastMessageAt?.toLocaleTimeString("ko-KR") ?? "-"}
                        </div>
                    </div>
                </div>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
                <MetricCard label="미처리" value={counts.open} className="border-rose-200 bg-rose-50" />
                <MetricCard label="처리 중" value={counts.inProgress} className="border-amber-200 bg-amber-50" />
                <MetricCard label="긴급" value={counts.critical} className="border-violet-200 bg-violet-50" />
                <MetricCard label="SLA 초과" value={counts.slaBreached} className="border-red-300 bg-red-50" />
                <MetricCard label="담당자 미지정" value={counts.unassigned} className="border-slate-200 bg-slate-50" />
            </div>

            <div className="mt-5 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                    <FilterSelect
                        label="원본"
                        value={sourceFilter}
                        onChange={(value) => setSourceFilter(value as SourceFilter)}
                        options={[
                            ["", "전체"],
                            ["AI_ALERT", "AI 경보"],
                            ["GEOFENCE", "지오펜스"],
                            ["FLIGHT_QUALITY", "기체 신뢰도"],
                            ["FLIGHT_GATE", "비행 시작 차단"],
                        ]}
                    />
                    <FilterSelect
                        label="우선순위"
                        value={priorityFilter}
                        onChange={(value) => setPriorityFilter(value as PriorityFilter)}
                        options={[
                            ["", "전체"],
                            ["CRITICAL", "긴급"],
                            ["HIGH", "높음"],
                            ["MEDIUM", "보통"],
                            ["LOW", "낮음"],
                        ]}
                    />
                    <FilterSelect
                        label="상태"
                        value={statusFilter}
                        onChange={(value) => setStatusFilter(value as StatusFilter)}
                        options={[
                            ["", "전체"],
                            ["OPEN", "미처리"],
                            ["IN_PROGRESS", "처리 중"],
                            ["RESOLVED", "해결"],
                            ["CLOSED", "종료"],
                        ]}
                    />
                    <label className="text-xs font-semibold text-slate-600">
                        담당자
                        <input
                            value={assigneeFilter}
                            onChange={(event) => setAssigneeFilter(event.target.value)}
                            maxLength={100}
                            placeholder="전체"
                            className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                        />
                    </label>
                    <div className="flex items-end gap-2">
                        <button
                            type="button"
                            onClick={() => void refreshIncidents()}
                            disabled={refreshing}
                            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
                        >
                            {refreshing ? "조회 중" : "새로고침"}
                        </button>
                        <label className="flex items-center gap-2 pb-2 text-xs text-slate-600">
                            <input
                                type="checkbox"
                                checked={autoRefresh}
                                onChange={(event) => setAutoRefresh(event.target.checked)}
                            />
                            자동
                        </label>
                    </div>
                </div>
            </div>

            {listError && (
                <div className="mt-4 rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-900">
                    {listError}
                </div>
            )}

            <div className="mt-5 grid gap-3 lg:grid-cols-2">
                {incidents.map((incident) => {
                    const priorityView = priorityPresentation(incident.priority);
                    const statusView = statusPresentation(incident.status);
                    const slaView = slaPresentation(incident, nowMs);

                    return (
                        <button
                            key={incident.id}
                            type="button"
                            onClick={() => openDetail(incident.id)}
                            className="rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:border-slate-400 hover:shadow-md"
                        >
                            <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                    <div className="text-xs font-semibold text-slate-500">
                                        #{incident.id} · {sourceLabel(incident.sourceType)} #{incident.sourceId}
                                    </div>
                                    <div className="mt-1 break-words font-bold text-slate-950">
                                        {incident.title}
                                    </div>
                                </div>
                                <div className="flex shrink-0 flex-wrap justify-end gap-1">
                                    <span className={`rounded-full px-2 py-1 text-[10px] font-bold ${priorityView.className}`}>
                                        {priorityView.label}
                                    </span>
                                    <span className={`rounded-full px-2 py-1 text-[10px] font-bold ${statusView.className}`}>
                                        {statusView.label}
                                    </span>
                                    <span className={`rounded-full px-2 py-1 text-[10px] font-bold ${slaView.className}`}>
                                        {slaView.label}
                                    </span>
                                </div>
                            </div>
                            <p className="mt-3 line-clamp-2 text-sm leading-6 text-slate-600">
                                {incident.summary}
                            </p>
                            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                                <span>드론 #{incident.droneId}</span>
                                <span>담당 {incident.assignee ?? "미지정"}</span>
                                <span>{formatKoreanDateTime(incident.occurredAt)}</span>
                            </div>
                        </button>
                    );
                })}
            </div>

            {!listError && incidents.length === 0 && (
                <div className="mt-5 rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
                    조회 조건에 해당하는 Incident가 없습니다.
                </div>
            )}

            {selectedIncidentId !== null && (
                <div className="fixed inset-0 z-50 overflow-y-auto bg-slate-950/60 p-4 sm:p-8">
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="incident-detail-title"
                        className="mx-auto max-w-5xl rounded-3xl bg-white p-5 shadow-2xl sm:p-7"
                    >
                        <div className="flex items-start justify-between gap-4">
                            <div>
                                <div className="text-xs font-bold uppercase tracking-wider text-rose-700">
                                    Incident #{selectedIncidentId}
                                </div>
                                <h3 id="incident-detail-title" className="mt-1 text-2xl font-bold text-slate-950">
                                    {selected?.title ?? "Incident 상세"}
                                </h3>
                            </div>
                            <div className="flex flex-wrap gap-2">
                                {selected && (
                                    <Link
                                        href={`/incidents/${selected.id}/report`}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-bold text-white hover:bg-slate-700"
                                    >
                                        Incident 보고서
                                    </Link>
                                )}
                                <button
                                    type="button"
                                    onClick={closeDetail}
                                    disabled={busyAction !== null}
                                    aria-label="Incident 상세 닫기"
                                    className="rounded-lg bg-slate-100 px-3 py-2 text-sm font-bold text-slate-700 disabled:opacity-50"
                                >
                                    닫기
                                </button>
                            </div>
                        </div>

                        {detailLoading && !detail && (
                            <div className="mt-6 rounded-xl bg-slate-50 p-6 text-center text-sm text-slate-500">
                                상세 정보를 불러오는 중입니다.
                            </div>
                        )}
                        {detailError && (
                            <div className="mt-5 rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-900">
                                {detailError}
                            </div>
                        )}

                        {selected && detail && (
                            <div className="mt-6 space-y-6">
                                <div className="grid gap-4 rounded-2xl bg-slate-50 p-5 md:grid-cols-2 xl:grid-cols-4">
                                    <DetailValue label="원본" value={`${sourceLabel(selected.sourceType)} #${selected.sourceId}`} />
                                    <DetailValue label="드론" value={`#${selected.droneId}`} />
                                    <DetailValue label="담당자" value={selected.assignee ?? "미지정"} />
                                    <DetailValue label="발생 시각" value={formatKoreanDateTime(selected.occurredAt)} />
                                    <DetailValue label="우선순위" value={priorityPresentation(selected.priority).label} />
                                    <DetailValue label="상태" value={statusPresentation(selected.status).label} />
                                    <DetailValue label="SLA 상태" value={slaPresentation(selected, nowMs).label} />
                                    <DetailValue
                                        label="SLA 기한"
                                        value={selected.slaDueAt
                                            ? formatKoreanDateTime(selected.slaDueAt)
                                            : "-"}
                                    />
                                    <DetailValue label="에스컬레이션" value={`${selected.escalationLevel}회`} />
                                    <DetailValue label="비행 세션" value={selected.sessionId ?? "-"} breakAll />
                                    <DetailValue label="최종 변경" value={formatKoreanDateTime(selected.updatedAt)} />
                                </div>

                                <div className="rounded-2xl border border-slate-200 p-5">
                                    <div className="text-sm font-bold text-slate-900">상황 요약</div>
                                    <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-600">
                                        {selected.summary}
                                    </p>
                                </div>

                                <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-violet-200 bg-violet-50 p-5">
                                    <div>
                                        <div className="font-bold text-violet-950">
                                            발생 증거 연결
                                        </div>
                                        <div className="mt-1 text-sm text-violet-800">
                                            {locationSourceLabel(detail.context.locationSource)}
                                            {detail.context.locationRecordedAt
                                                ? ` · ${formatKoreanDateTime(detail.context.locationRecordedAt)}`
                                                : ""}
                                        </div>
                                        <div className="mt-1 text-xs text-violet-700">
                                            {detail.context.replayAvailable
                                                ? "저장된 비행 경로를 불러와 Incident 발생 시각으로 이동합니다."
                                                : "연결된 비행 세션이 없어 드론과 확보된 위치만 표시합니다."}
                                        </div>
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                        {detail.context.snapshotAvailable &&
                                            detail.context.snapshotUrl && (
                                                <Link
                                                    href={detail.context.snapshotUrl}
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    className="rounded-lg border border-violet-300 bg-white px-4 py-2 text-sm font-bold text-violet-800 hover:bg-violet-100"
                                                >
                                                    AI 스냅샷
                                                </Link>
                                            )}
                                        <Link
                                            href={buildIncidentNavigationHref(detail)}
                                            className="rounded-lg bg-violet-800 px-4 py-2 text-sm font-bold text-white hover:bg-violet-700"
                                        >
                                            {detail.context.replayAvailable
                                                ? "발생 시각 재생"
                                                : "관제 지도에서 확인"}
                                        </Link>
                                    </div>
                                </div>

                                <div className="grid gap-4 xl:grid-cols-2">
                                    <div className="space-y-4 rounded-2xl border border-slate-200 p-5">
                                        <h4 className="font-bold text-slate-900">관제 처리</h4>
                                        {!canOperate && operateDeniedReason && (
                                            <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-900">
                                                {operateDeniedReason}
                                            </div>
                                        )}
                                        <label className="block text-xs font-semibold text-slate-600">
                                            처리자
                                            <input
                                                value={operator}
                                                onChange={(event) => setOperator(event.target.value)}
                                                maxLength={100}
                                                disabled={!canOperate || busyAction !== null}
                                                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                                            />
                                        </label>

                                        <div className="flex gap-2">
                                            <input
                                                value={assignee}
                                                onChange={(event) => setAssignee(event.target.value)}
                                                maxLength={100}
                                                disabled={!canOperate || busyAction !== null}
                                                placeholder="담당자"
                                                className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
                                            />
                                            <ActionButton
                                                label="담당 지정"
                                                busy={busyAction === "ASSIGNEE"}
                                                disabled={!canOperate || !operator.trim() || !assignee.trim()}
                                                onClick={() => void submitAction("ASSIGNEE", "assignee", "PATCH", { assignee: assignee.trim(), actor: operator.trim() }, "담당자를 지정했습니다.")}
                                            />
                                        </div>

                                        <div className="flex gap-2">
                                            <select
                                                value={priority}
                                                disabled={!canOperate || busyAction !== null}
                                                onChange={(event) => setPriority(event.target.value as IncidentPriority)}
                                                className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
                                            >
                                                {PRIORITIES.map((value) => (
                                                    <option key={value} value={value}>
                                                        {priorityPresentation(value).label}
                                                    </option>
                                                ))}
                                            </select>
                                            <ActionButton
                                                label="우선순위 변경"
                                                busy={busyAction === "PRIORITY"}
                                                disabled={!canOperate || !operator.trim() || priority === selected.priority}
                                                onClick={() => void submitAction("PRIORITY", "priority", "PATCH", { priority, actor: operator.trim(), note: actionNote.trim() }, "우선순위를 변경했습니다.")}
                                            />
                                        </div>

                                        <div className="flex gap-2">
                                            <select
                                                value={nextStatus}
                                                onChange={(event) => setNextStatus(event.target.value as IncidentStatus)}
                                                disabled={!canOperate || busyAction !== null || availableStatuses.length === 0}
                                                className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100"
                                            >
                                                {availableStatuses.length > 0 ? (
                                                    availableStatuses.map((value) => (
                                                        <option key={value} value={value}>
                                                            {statusPresentation(value).label}
                                                        </option>
                                                    ))
                                                ) : (
                                                    <option value={selected.status}>변경 불가</option>
                                                )}
                                            </select>
                                            <ActionButton
                                                label="상태 변경"
                                                busy={busyAction === "STATUS"}
                                                disabled={!canOperate || !operator.trim() || availableStatuses.length === 0}
                                                onClick={() => void submitAction("STATUS", "status", "PATCH", { status: nextStatus, actor: operator.trim(), note: actionNote.trim() }, "처리 상태를 변경했습니다.")}
                                            />
                                        </div>

                                        <textarea
                                            value={actionNote}
                                            onChange={(event) => setActionNote(event.target.value)}
                                            maxLength={1000}
                                            rows={2}
                                            disabled={!canOperate || busyAction !== null}
                                            placeholder="우선순위·상태 변경 사유(선택)"
                                            className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                                        />
                                    </div>

                                    <div className="rounded-2xl border border-slate-200 p-5">
                                        <h4 className="font-bold text-slate-900">조치 메모 추가</h4>
                                        <textarea
                                            value={journalNote}
                                            onChange={(event) => setJournalNote(event.target.value)}
                                            maxLength={1000}
                                            rows={6}
                                            disabled={!canOperate || busyAction !== null}
                                            placeholder="현장 확인, 연락, 분석 결과 등을 기록하세요."
                                            className="mt-4 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                                        />
                                        <div className="mt-3 flex justify-end">
                                            <ActionButton
                                                label="메모 저장"
                                                busy={busyAction === "NOTE"}
                                                disabled={!canOperate || !operator.trim() || !journalNote.trim()}
                                                onClick={() => void submitAction("NOTE", "notes", "POST", { actor: operator.trim(), note: journalNote.trim() }, "조치 메모를 저장했습니다.")}
                                            />
                                        </div>
                                    </div>
                                </div>

                                {actionMessage && (
                                    <div className="rounded-xl border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900">
                                        {actionMessage}
                                    </div>
                                )}
                                {actionError && (
                                    <div className="rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-900">
                                        {actionError}
                                    </div>
                                )}

                                <div className="rounded-2xl border border-slate-200 p-5">
                                    <h4 className="font-bold text-slate-900">조치 이력</h4>
                                    <div className="mt-4 space-y-3">
                                        {detail.history.map((history) => (
                                            <div key={history.id} className="rounded-xl bg-slate-50 p-4">
                                                <div className="flex flex-wrap items-center justify-between gap-2">
                                                    <div className="text-sm font-bold text-slate-800">
                                                        {history.actionType}
                                                        {history.previousStatus && history.newStatus
                                                            ? ` · ${history.previousStatus} → ${history.newStatus}`
                                                            : ""}
                                                    </div>
                                                    <div className="text-xs text-slate-500">
                                                        {formatKoreanDateTime(history.createdAt)}
                                                    </div>
                                                </div>
                                                <div className="mt-1 text-xs text-slate-500">처리자 {history.actor}</div>
                                                {history.note && (
                                                    <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">
                                                        {history.note}
                                                    </p>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </section>
    );
}

function MetricCard({
    label,
    value,
    className,
}: {
    label: string;
    value: number;
    className: string;
}) {
    return (
        <div className={`rounded-2xl border p-4 shadow-sm ${className}`}>
            <div className="text-xs font-semibold text-slate-600">{label}</div>
            <div className="mt-1 text-2xl font-bold text-slate-950">{value}건</div>
        </div>
    );
}

function FilterSelect({
    label,
    value,
    onChange,
    options,
}: {
    label: string;
    value: string;
    onChange: (value: string) => void;
    options: Array<[string, string]>;
}) {
    return (
        <label className="text-xs font-semibold text-slate-600">
            {label}
            <select
                value={value}
                onChange={(event) => onChange(event.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
            >
                {options.map(([optionValue, optionLabel]) => (
                    <option key={optionValue || "ALL"} value={optionValue}>
                        {optionLabel}
                    </option>
                ))}
            </select>
        </label>
    );
}

function DetailValue({
    label,
    value,
    breakAll = false,
}: {
    label: string;
    value: string;
    breakAll?: boolean;
}) {
    return (
        <div>
            <div className="text-xs font-semibold text-slate-500">{label}</div>
            <div className={`mt-1 text-sm font-bold text-slate-900 ${breakAll ? "break-all" : ""}`}>
                {value}
            </div>
        </div>
    );
}

function ActionButton({
    label,
    busy,
    disabled,
    onClick,
}: {
    label: string;
    busy: boolean;
    disabled: boolean;
    onClick: () => void;
}) {
    return (
        <button
            type="button"
            onClick={onClick}
            disabled={busy || disabled}
            className="shrink-0 rounded-lg bg-slate-900 px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-40"
        >
            {busy ? "처리 중" : label}
        </button>
    );
}
