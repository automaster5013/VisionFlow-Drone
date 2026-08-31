import Link from "next/link";

import { AiPerformancePanel } from "@/components/dashboard/ai-performance-panel";
import { FlightPerformanceTrendPanel } from "@/components/dashboard/flight-performance-trend-panel";
import { formatKoreanDateTime } from "@/lib/date";
import type {
    DashboardAiAlertItem,
    DashboardFilterFormValues,
    DashboardFlightGateAction,
    DashboardFlightGateDecisionItem,
    DashboardFlightSessionItem,
    DashboardFlightSessionStatus,
    OperationsDashboardData,
} from "@/types/operations-dashboard";

interface OperationsDashboardProps {
    data: OperationsDashboardData | null;
    errorMessage: string | null;
    filterValues: DashboardFilterFormValues;
}

function formatDuration(totalSeconds: number): string {
    const safeSeconds = Math.max(0, Math.round(totalSeconds));
    const hours = Math.floor(safeSeconds / 3600);
    const minutes = Math.floor((safeSeconds % 3600) / 60);
    const seconds = safeSeconds % 60;

    if (hours > 0) {
        return `${hours}시간 ${minutes}분`;
    }

    return `${minutes}분 ${seconds}초`;
}

function statusPresentation(status: DashboardFlightSessionStatus) {
    return {
        READY: {
            label: "준비",
            className: "bg-sky-100 text-sky-800",
        },
        ACTIVE: {
            label: "비행 중",
            className: "bg-emerald-100 text-emerald-800",
        },
        COMPLETED: {
            label: "완료",
            className: "bg-indigo-100 text-indigo-800",
        },
        ABORTED: {
            label: "중단",
            className: "bg-rose-100 text-rose-800",
        },
    }[status];
}

function flightGatePresentation(action: DashboardFlightGateAction) {
    return {
        MAINTENANCE_FLIGHT_START_ALLOWED: {
            label: "허용",
            className: "bg-emerald-100 text-emerald-800",
        },
        MAINTENANCE_FLIGHT_START_ADVISORY: {
            label: "주의 허용",
            className: "bg-amber-100 text-amber-800",
        },
        MAINTENANCE_FLIGHT_START_BLOCKED: {
            label: "차단",
            className: "bg-rose-100 text-rose-800",
        },
    }[action];
}

export function OperationsDashboard({
    data,
    errorMessage,
    filterValues,
}: OperationsDashboardProps) {
    return (
        <section
            aria-labelledby="operations-dashboard-title"
            className="vf-operations-dashboard"
        >
            <div className="vf-operations-dashboard__hero flex flex-wrap items-end justify-between gap-3">
                <div>
                    <p className="text-sm font-semibold uppercase tracking-wider text-cyan-700">
                        Operations Overview
                    </p>
                    <h1
                        id="operations-dashboard-title"
                        className="mt-2 text-3xl font-bold tracking-tight text-slate-950"
                    >
                        실시간 운영 대시보드
                    </h1>
                    <p className="mt-2 text-sm leading-6 text-slate-600">
                        비행 세션 수명주기와 YOLO 탐지 현황을 한 화면에서 확인합니다.
                    </p>
                </div>

                {data && (
                    <div className="text-right text-xs text-slate-500">
                        <div className="font-semibold text-slate-700">최근 집계</div>
                        <div className="mt-1">
                            {formatKoreanDateTime(data.generatedAt)}
                        </div>
                    </div>
                )}
            </div>

            <AiPerformancePanel />

            <article className="vf-command-panel vf-command-panel--accent mt-6 rounded-2xl border border-cyan-200 bg-white p-5 shadow-sm">
                <div>
                    <h2 className="text-lg font-bold text-slate-900">
                        운영 데이터 필터
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">
                        드론·세션 상태·한국 날짜 기준 조회 기간을 선택합니다.
                    </p>
                </div>

                <form
                    action="/dashboard"
                    method="get"
                    className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5"
                >
                    <label className="text-sm font-semibold text-slate-700">
                        드론 ID
                        <input
                            type="number"
                            name="droneId"
                            min={1}
                            step={1}
                            defaultValue={filterValues.droneId}
                            placeholder="전체 드론"
                            className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-normal text-slate-900"
                        />
                    </label>

                    <label className="text-sm font-semibold text-slate-700">
                        세션 상태
                        <select
                            name="status"
                            defaultValue={filterValues.status}
                            className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-normal text-slate-900"
                        >
                            <option value="">전체 상태</option>
                            <option value="READY">준비</option>
                            <option value="ACTIVE">비행 중</option>
                            <option value="COMPLETED">완료</option>
                            <option value="ABORTED">중단</option>
                        </select>
                    </label>

                    <label className="text-sm font-semibold text-slate-700">
                        시작일
                        <input
                            type="date"
                            name="from"
                            defaultValue={filterValues.from}
                            className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-normal text-slate-900"
                        />
                    </label>

                    <label className="text-sm font-semibold text-slate-700">
                        종료일
                        <input
                            type="date"
                            name="to"
                            defaultValue={filterValues.to}
                            className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-normal text-slate-900"
                        />
                    </label>

                    <label className="text-sm font-semibold text-slate-700">
                        최근 목록
                        <select
                            name="limit"
                            defaultValue={filterValues.limit}
                            className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-normal text-slate-900"
                        >
                            <option value="5">5개</option>
                            <option value="10">10개</option>
                            <option value="20">20개</option>
                        </select>
                    </label>

                    <div className="flex flex-wrap gap-2 md:col-span-2 xl:col-span-5 xl:justify-end">
                        <Link
                            href="/dashboard"
                            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700 hover:border-slate-400"
                        >
                            필터 초기화
                        </Link>
                        <button
                            type="submit"
                            className="rounded-lg bg-cyan-700 px-4 py-2 text-sm font-bold text-white hover:bg-cyan-600"
                        >
                            조회 적용
                        </button>
                    </div>
                </form>

                <p className="mt-3 text-xs text-slate-500">
                    상태 필터는 비행 세션에만 적용됩니다. AI 집계는 선택한 드론과
                    기간 조건을 사용하며, 비행 게이트 이력에는 드론·기간 조건이
                    적용됩니다.
                </p>
            </article>

            {errorMessage && (
                <div className="mt-6 rounded-2xl border border-red-300 bg-red-50 p-5 text-red-900">
                    <div className="font-bold">운영 집계를 불러오지 못했습니다.</div>
                    <div className="mt-2 break-words text-sm">{errorMessage}</div>
                    <div className="mt-2 text-xs text-red-700">
                        Spring Boot의 `/api/dashboard/operations` 상태를 확인하세요.
                    </div>
                </div>
            )}

            {data && (
                <div className="mt-6 space-y-5">
                    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                        <MetricCard
                            label="전체 비행 세션"
                            value={`${data.flightSessions.total}개`}
                            description={`완료 ${data.flightSessions.completed} · 준비 ${data.flightSessions.ready}`}
                            className="border-sky-200 bg-sky-50"
                        />
                        <MetricCard
                            label="현재 비행 중"
                            value={`${data.flightSessions.active}개`}
                            description="ACTIVE 상태 세션"
                            className="border-emerald-200 bg-emerald-50"
                        />
                        <MetricCard
                            label="중단된 세션"
                            value={`${data.flightSessions.aborted}개`}
                            description="ABORTED 누적 세션"
                            className="border-rose-200 bg-rose-50"
                        />
                        <MetricCard
                            label="AI 총 탐지"
                            value={`${data.aiInference.totalDetections}개`}
                            description={`탐지 프레임 ${data.aiInference.detectedEvents} / 추론 ${data.aiInference.totalEvents}`}
                            className="border-violet-200 bg-violet-50"
                        />
                    </div>

                    <article className="rounded-2xl border border-amber-200 bg-white p-5 shadow-sm">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                                <h2 className="text-lg font-bold text-amber-950">
                                    정비 기반 비행 시작 판단
                                </h2>
                                <p className="mt-1 text-sm text-slate-500">
                                    실제 비행 시작 요청에서 기록된 허용·주의·차단
                                    감사 이력입니다.
                                </p>
                            </div>
                            <Link
                                href="/audit-logs?entityType=MAINTENANCE_FLIGHT_GATE"
                                className="rounded-lg bg-amber-700 px-3 py-2 text-sm font-bold text-white hover:bg-amber-600"
                            >
                                전체 감사 로그
                            </Link>
                        </div>

                        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                            <StatusCount
                                label="전체 판단"
                                count={data.flightGate.total}
                            />
                            <StatusCount
                                label="시작 허용"
                                count={data.flightGate.allowed}
                            />
                            <StatusCount
                                label="주의 허용"
                                count={data.flightGate.advisory}
                            />
                            <StatusCount
                                label="시작 차단"
                                count={data.flightGate.blocked}
                            />
                        </div>

                        {data.recentFlightGateDecisions.length > 0 ? (
                            <div className="mt-4 grid gap-3 lg:grid-cols-2">
                                {data.recentFlightGateDecisions.map(
                                    (decision) => (
                                        <FlightGateDecisionCard
                                            key={decision.auditId}
                                            decision={decision}
                                        />
                                    ),
                                )}
                            </div>
                        ) : (
                            <EmptyState message="아직 기록된 비행 시작 판단이 없습니다." />
                        )}
                    </article>

                    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                            <div>
                                <h2 className="text-lg font-bold text-slate-900">
                                    비행 세션 상태
                                </h2>
                                <p className="mt-1 text-sm text-slate-500">
                                    전체 관리 세션의 현재 상태 분포입니다.
                                </p>
                            </div>
                            <div className="flex flex-wrap gap-2">
                                <Link
                                    href="/fleet-reliability"
                                    className="rounded-lg bg-cyan-700 px-3 py-2 text-sm font-bold text-white hover:bg-cyan-600"
                                >
                                    기체 신뢰도
                                </Link>
                                <Link
                                    href="/flight-comparison"
                                    className="rounded-lg bg-violet-700 px-3 py-2 text-sm font-bold text-white hover:bg-violet-600"
                                >
                                    비행 비교 분석
                                </Link>
                                <Link
                                    href="/drones"
                                    className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-bold text-white hover:bg-slate-700"
                                >
                                    드론 관제 열기
                                </Link>
                            </div>
                        </div>

                        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
                            <StatusCount label="전체" count={data.flightSessions.total} />
                            <StatusCount label="준비" count={data.flightSessions.ready} />
                            <StatusCount label="비행 중" count={data.flightSessions.active} />
                            <StatusCount label="완료" count={data.flightSessions.completed} />
                            <StatusCount label="중단" count={data.flightSessions.aborted} />
                        </div>
                    </article>

                    <FlightPerformanceTrendPanel sessions={data.recentSessions} />

                    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                        <div>
                            <h2 className="text-lg font-bold text-slate-900">
                                최근 비행 세션
                            </h2>
                            <p className="mt-1 text-sm text-slate-500">
                                최근 생성·수정된 관리 세션입니다.
                            </p>
                        </div>

                        {data.recentSessions.length > 0 ? (
                            <div className="mt-4 grid gap-3 lg:grid-cols-2">
                                {data.recentSessions.map((session) => (
                                    <FlightSessionCard
                                        key={session.sessionId}
                                        session={session}
                                    />
                                ))}
                            </div>
                        ) : (
                            <EmptyState message="저장된 비행 세션이 없습니다." />
                        )}
                    </article>

                    <div className="grid gap-5 xl:grid-cols-2">
                        <article className="rounded-2xl border border-rose-200 bg-white p-5 shadow-sm">
                            <div>
                                <h2 className="text-lg font-bold text-rose-950">
                                    최근 중단 세션
                                </h2>
                                <p className="mt-1 text-sm text-slate-500">
                                    원인 확인이 필요한 최근 ABORTED 세션입니다.
                                </p>
                            </div>

                            {data.recentAbortedSessions.length > 0 ? (
                                <div className="mt-4 space-y-3">
                                    {data.recentAbortedSessions.map((session) => (
                                        <FlightSessionCard
                                            key={session.sessionId}
                                            session={session}
                                            compact
                                        />
                                    ))}
                                </div>
                            ) : (
                                <EmptyState message="중단된 세션이 없습니다." />
                            )}
                        </article>

                        <article className="rounded-2xl border border-violet-200 bg-white p-5 shadow-sm">
                            <div>
                                <h2 className="text-lg font-bold text-violet-950">
                                    최근 AI 탐지 알림
                                </h2>
                                <p className="mt-1 text-sm text-slate-500">
                                    객체가 한 개 이상 탐지된 최근 추론 이벤트입니다.
                                </p>
                            </div>

                            {data.recentAiAlerts.length > 0 ? (
                                <div className="mt-4 space-y-3">
                                    {data.recentAiAlerts.map((alert) => (
                                        <AiAlertCard key={alert.eventId} alert={alert} />
                                    ))}
                                </div>
                            ) : (
                                <EmptyState message="AI 탐지 알림이 없습니다." />
                            )}
                        </article>
                    </div>
                </div>
            )}
        </section>
    );
}

function MetricCard({
    label,
    value,
    description,
    className,
}: {
    label: string;
    value: string;
    description: string;
    className: string;
}) {
    return (
        <article className={`vf-command-metric rounded-2xl border p-5 shadow-sm ${className}`}>
            <div className="text-sm font-semibold text-slate-600">{label}</div>
            <div className="mt-2 text-3xl font-bold text-slate-950">{value}</div>
            <div className="mt-2 text-xs text-slate-500">{description}</div>
        </article>
    );
}

function StatusCount({ label, count }: { label: string; count: number }) {
    return (
        <div className="vf-command-counter rounded-xl bg-slate-50 p-3 text-center">
            <div className="text-xs font-semibold text-slate-500">{label}</div>
            <div className="mt-1 text-xl font-bold text-slate-900">{count}</div>
        </div>
    );
}

function FlightSessionCard({
    session,
    compact = false,
}: {
    session: DashboardFlightSessionItem;
    compact?: boolean;
}) {
    const presentation = statusPresentation(session.status);
    const replayHref =
        `/drones?droneId=${session.droneId}` +
        `&sessionId=${encodeURIComponent(session.sessionId)}` +
        "#flight-session-replay";
    const reportHref =
        `/drones/${session.droneId}/flight-sessions/` +
        `${encodeURIComponent(session.sessionId)}/report`;
    const reportAvailable =
        session.status === "COMPLETED" || session.status === "ABORTED";

    return (
        <div className="vf-command-record rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <div className="break-words font-bold text-slate-900">
                        {session.name}
                    </div>
                    <div className="mt-1 break-all font-mono text-[11px] text-slate-500">
                        {session.sessionId}
                    </div>
                </div>
                <span
                    className={`shrink-0 rounded-full px-2 py-1 text-[10px] font-bold ${presentation.className}`}
                >
                    {presentation.label}
                </span>
            </div>

            {!compact && session.description && (
                <div className="mt-2 break-words text-sm text-slate-600">
                    {session.description}
                </div>
            )}

            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
                <span>드론 #{session.droneId}</span>
                <span>비행 {formatDuration(session.durationSeconds)}</span>
                <span>
                    {formatKoreanDateTime(session.endedAt ?? session.startedAt)}
                </span>
            </div>

            <div className="mt-3 flex flex-wrap justify-end gap-2 border-t border-slate-200 pt-3">
                {reportAvailable && (
                    <Link
                        href={reportHref}
                        className="inline-flex rounded-lg bg-violet-700 px-3 py-2 text-xs font-bold text-white hover:bg-violet-600"
                    >
                        종합 보고서
                    </Link>
                )}
                <Link
                    href={replayHref}
                    className="inline-flex rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white hover:bg-slate-700"
                >
                    상세 관제 및 경로 재생
                </Link>
            </div>
        </div>
    );
}

function AiAlertCard({ alert }: { alert: DashboardAiAlertItem }) {
    return (
        <div className="vf-command-record vf-command-record--ai rounded-xl border border-violet-100 bg-violet-50 p-4">
            <div className="flex items-start justify-between gap-3">
                <div>
                    <div className="font-bold text-violet-950">
                        드론 #{alert.droneId} · 탐지 {alert.detectionCount}개
                    </div>
                    <div className="mt-1 text-xs text-violet-700">
                        {formatKoreanDateTime(alert.capturedAt)} · 프레임 #{alert.frameIndex}
                    </div>
                </div>
                {alert.snapshotAvailable && (
                    <a
                        href={`/api/ai/events/${alert.eventId}/snapshot`}
                        target="_blank"
                        rel="noreferrer"
                        className="shrink-0 rounded-lg bg-violet-700 px-3 py-1.5 text-xs font-bold text-white hover:bg-violet-600"
                    >
                        스냅샷
                    </a>
                )}
            </div>
            <div className="mt-2 break-all font-mono text-[11px] text-slate-500">
                {alert.sessionId} · {alert.sourceId}
            </div>
        </div>
    );
}

function FlightGateDecisionCard({
    decision,
}: {
    decision: DashboardFlightGateDecisionItem;
}) {
    const presentation = flightGatePresentation(decision.action);
    const auditHref =
        `/audit-logs?entityType=MAINTENANCE_FLIGHT_GATE` +
        `&entityId=${decision.droneId}`;

    return (
        <div className="vf-command-record vf-command-record--warning rounded-xl border border-amber-100 bg-amber-50 p-4">
            <div className="flex items-start justify-between gap-3">
                <div>
                    <div className="font-bold text-amber-950">
                        드론 #{decision.droneId}
                    </div>
                    <div className="mt-1 text-xs text-amber-800">
                        {formatKoreanDateTime(decision.occurredAt)}
                    </div>
                </div>
                <span
                    className={`shrink-0 rounded-full px-2 py-1 text-[10px] font-bold ${presentation.className}`}
                >
                    {presentation.label}
                </span>
            </div>
            <div className="mt-2 text-sm text-slate-700">
                {decision.summary}
            </div>
            <div className="mt-3 flex justify-end border-t border-amber-100 pt-3">
                <Link
                    href={auditHref}
                    className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white hover:bg-slate-700"
                >
                    기체 감사 이력
                </Link>
            </div>
        </div>
    );
}

function EmptyState({ message }: { message: string }) {
    return (
        <div className="vf-command-empty mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">
            {message}
        </div>
    );
}
