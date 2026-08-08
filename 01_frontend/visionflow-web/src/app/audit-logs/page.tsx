import type { Metadata } from "next";
import Link from "next/link";

import { AuditExportLink } from "@/components/audit/audit-export-link";

import { getAuditRetentionStatus } from "@/lib/api/audit-retention";
import { getAuditLogs } from "@/lib/api/audit-logs";
import {
    buildProtectedReturnTo,
    requireOperatorAuthentication,
} from "@/lib/server/protected-page";
import { formatKoreanDateTime } from "@/lib/date";
import {
    AUDIT_ACTIONS,
    AUDIT_ENTITY_TYPES,
    isAuditAction,
    isAuditEntityType,
    type AuditAction,
    type AuditEntityType,
    type AuditLogPage,
    type AuditLogQuery,
} from "@/types/audit-log";
import type { AuditRetentionStatus } from "@/types/audit-retention";

export const metadata: Metadata = {
    title: "운영 감사 로그",
};

export const dynamic = "force-dynamic";

type SearchValue = string | string[] | undefined;

interface AuditLogPageProps {
    searchParams: Promise<Record<string, SearchValue>>;
}

interface FilterValues {
    action: string;
    entityType: string;
    entityId: string;
    actor: string;
    from: string;
    to: string;
    size: string;
}

const ACTION_LABELS: Record<AuditAction, string> = {
    FLIGHT_SESSION_STARTED: "비행 세션 시작",
    FLIGHT_SESSION_UPDATED: "비행 세션 수정",
    FLIGHT_SESSION_COMPLETED: "비행 세션 완료",
    FLIGHT_SESSION_ABORTED: "비행 세션 중단",
    FLIGHT_QUALITY_ASSESSED: "비행 품질 평가",
    FLIGHT_QUALITY_INCIDENT_SYNCHRONIZED:
        "기체 신뢰도 Incident 동기화",
    MAINTENANCE_WORK_ORDER_SYNCHRONIZED: "점검 작업 동기화",
    MAINTENANCE_INSPECTION_STARTED: "기체 점검 시작",
    MAINTENANCE_RETURN_TO_SERVICE_APPROVED: "재운항 승인",
    MAINTENANCE_DRONE_GROUNDED: "기체 운항 중지",
    MAINTENANCE_FLIGHT_START_ALLOWED: "정비 게이트 비행 시작 허용",
    MAINTENANCE_FLIGHT_START_ADVISORY: "정비 게이트 주의 허용",
    MAINTENANCE_FLIGHT_START_BLOCKED: "정비 게이트 비행 시작 차단",
    MAINTENANCE_FLIGHT_GATE_INCIDENT_SYNCHRONIZED:
        "비행 게이트 Incident 동기화",
    GEOFENCE_CREATED: "지오펜스 생성",
    GEOFENCE_UPDATED: "지오펜스 수정",
    GEOFENCE_ACTIVATED: "지오펜스 활성화",
    GEOFENCE_DEACTIVATED: "지오펜스 비활성화",
    INCIDENT_ASSIGNED: "Incident 담당자 지정",
    INCIDENT_PRIORITY_CHANGED: "Incident 우선순위 변경",
    INCIDENT_STATUS_CHANGED: "Incident 상태 변경",
    INCIDENT_NOTE_ADDED: "Incident 메모 추가",
    DEMO_SCENARIO_STARTED: "시연 시작",
    DEMO_SCENARIO_DETECTED: "시연 AI 탐지",
    DEMO_SCENARIO_ESCALATED: "시연 SLA 승격",
    DEMO_SCENARIO_RESOLVED: "시연 해결",
    DEMO_SCENARIO_COMPLETED: "시연 완료",
    OPERATOR_LOGIN_SUCCEEDED: "운영자 로그인 성공",
    OPERATOR_LOGIN_FAILED: "운영자 로그인 실패",
    OPERATOR_LOGIN_LOCKED: "운영자 로그인 일시 잠금",
    OPERATOR_LOGOUT: "운영자 로그아웃",
    OPERATOR_SESSION_REVOKED: "운영자 세션 강제 종료",
    OPERATOR_SESSIONS_BULK_REVOKED: "운영자 다른 세션 일괄 종료",
    AUDIT_LOG_EXPORTED: "감사 로그 CSV 내보내기",
    AUDIT_LOG_RETENTION_EXECUTED: "감사 로그 보존 정리",
};

const ENTITY_LABELS: Record<AuditEntityType, string> = {
    FLIGHT_SESSION: "비행 세션",
    FLIGHT_QUALITY_ASSESSMENT: "비행 품질 평가",
    MAINTENANCE_WORK_ORDER: "점검 작업지시",
    MAINTENANCE_FLIGHT_GATE: "정비 비행 게이트",
    GEOFENCE: "지오펜스",
    INCIDENT: "Incident",
    DEMO_SCENARIO: "시연 시나리오",
    OPERATOR_SESSION: "운영자 세션",
    AUDIT_LOG: "감사 로그",
};

function first(value: SearchValue): string {
    return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
}

function isDateInput(value: string): boolean {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const [year, month, day] = value.split("-").map(Number);
    const date = new Date(Date.UTC(year, month - 1, day));
    return (
        date.getUTCFullYear() === year &&
        date.getUTCMonth() === month - 1 &&
        date.getUTCDate() === day
    );
}

function parseFilters(search: Record<string, SearchValue>): {
    values: FilterValues;
    query: AuditLogQuery;
    error: string | null;
} {
    const action = first(search.action).toUpperCase();
    const entityType = first(search.entityType).toUpperCase();
    const entityId = first(search.entityId);
    const actor = first(search.actor);
    const from = first(search.from);
    const to = first(search.to);
    const rawPage = first(search.page) || "0";
    const rawSize = first(search.size) || "30";
    const values = {
        action,
        entityType,
        entityId,
        actor,
        from,
        to,
        size: rawSize,
    };

    if (action && !isAuditAction(action)) {
        return { values, query: {}, error: "지원하지 않는 감사 작업입니다." };
    }
    if (entityType && !isAuditEntityType(entityType)) {
        return { values, query: {}, error: "지원하지 않는 감사 대상입니다." };
    }
    if (entityId.length > 100 || actor.length > 100) {
        return {
            values,
            query: {},
            error: "감사 대상 ID와 처리자는 100자 이하여야 합니다.",
        };
    }
    if ((from && !isDateInput(from)) || (to && !isDateInput(to))) {
        return { values, query: {}, error: "조회 기간이 올바르지 않습니다." };
    }
    if (from && to && from > to) {
        return {
            values,
            query: {},
            error: "조회 시작일은 종료일보다 늦을 수 없습니다.",
        };
    }
    if (!/^\d+$/.test(rawPage) || !/^\d+$/.test(rawSize)) {
        return { values, query: {}, error: "페이지 값이 올바르지 않습니다." };
    }
    const page = Number(rawPage);
    const size = Number(rawSize);
    if (page < 0 || ![20, 30, 50, 100].includes(size)) {
        return { values, query: {}, error: "페이지 또는 조회 개수가 올바르지 않습니다." };
    }

    return {
        values,
        query: {
            action: action && isAuditAction(action) ? action : undefined,
            entityType:
                entityType && isAuditEntityType(entityType)
                    ? entityType
                    : undefined,
            entityId: entityId || undefined,
            actor: actor || undefined,
            from: from ? `${from}T00:00:00+09:00` : undefined,
            to: to ? `${to}T23:59:59.999+09:00` : undefined,
            page,
            size,
        },
        error: null,
    };
}

function pageHref(values: FilterValues, page: number): string {
    const params = new URLSearchParams({ page: String(page), size: values.size });
    if (values.action) params.set("action", values.action);
    if (values.entityType) params.set("entityType", values.entityType);
    if (values.entityId) params.set("entityId", values.entityId);
    if (values.actor) params.set("actor", values.actor);
    if (values.from) params.set("from", values.from);
    if (values.to) params.set("to", values.to);
    return `/audit-logs?${params.toString()}`;
}

function exportHref(values: FilterValues): string {
    const params = new URLSearchParams({ limit: "5000" });
    if (values.action) params.set("action", values.action);
    if (values.entityType) params.set("entityType", values.entityType);
    if (values.entityId) params.set("entityId", values.entityId);
    if (values.actor) params.set("actor", values.actor);
    if (values.from) params.set("from", `${values.from}T00:00:00+09:00`);
    if (values.to) params.set("to", `${values.to}T23:59:59.999+09:00`);
    return `/api/audit-logs/export?${params.toString()}`;
}

function formatDetails(value: string | null): string {
    if (!value) return "-";
    try {
        const parsed: unknown = JSON.parse(value);
        return JSON.stringify(parsed);
    } catch {
        return value;
    }
}

async function loadAuditLogs(
    query: AuditLogQuery,
    validationError: string | null,
): Promise<{ data: AuditLogPage | null; error: string | null }> {
    if (validationError) return { data: null, error: validationError };
    try {
        return { data: await getAuditLogs(query), error: null };
    } catch (error) {
        return {
            data: null,
            error:
                error instanceof Error
                    ? error.message
                    : "감사 로그를 불러오지 못했습니다.",
        };
    }
}

async function loadRetentionStatus(): Promise<{
    data: AuditRetentionStatus | null;
    error: string | null;
}> {
    try {
        return { data: await getAuditRetentionStatus(), error: null };
    } catch (error) {
        return {
            data: null,
            error:
                error instanceof Error
                    ? error.message
                    : "감사 보존 정책을 불러오지 못했습니다.",
        };
    }
}

export default async function AuditLogsPage({
    searchParams,
}: AuditLogPageProps) {
    const search = await searchParams;
    await requireOperatorAuthentication(
        buildProtectedReturnTo("/audit-logs", search),
    );

    const parsed = parseFilters(search);
    const [result, retention] = await Promise.all([
        loadAuditLogs(parsed.query, parsed.error),
        loadRetentionStatus(),
    ]);
    const data = result.data;

    return (
        <div className="space-y-6">
            <header>
                <p className="text-sm font-semibold text-sky-700">OPERATION AUDIT</p>
                <h1 className="mt-1 text-3xl font-bold text-slate-950">
                    운영자 행위 감사 로그
                </h1>
                <p className="mt-2 text-sm text-slate-600">
                    비행 세션, 지오펜스, Incident, 발표 시연과 운영자 인증 이력을
                    시간순으로 확인합니다.
                </p>
            </header>

            <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                        <p className="text-sm font-semibold text-slate-900">
                            감사 로그 보존 정책
                        </p>
                        {retention.data ? (
                            <p className="mt-2 text-sm text-slate-600">
                                {retention.data.retentionDays}일 보존 · 1회 최대{" "}
                                {retention.data.batchSize.toLocaleString("ko-KR")}건 ·
                                정리 예정{" "}
                                {retention.data.eligibleCount.toLocaleString("ko-KR")}건
                            </p>
                        ) : null}
                    </div>
                    {retention.data ? (
                        <span
                            className={`rounded-full px-3 py-1 text-xs font-bold ${
                                retention.data.enabled &&
                                retention.data.archiveConfirmed
                                    ? "bg-amber-100 text-amber-800"
                                    : retention.data.enabled
                                      ? "bg-red-100 text-red-800"
                                      : "bg-emerald-100 text-emerald-800"
                            }`}
                        >
                            {retention.data.enabled &&
                            retention.data.archiveConfirmed
                                ? "ENABLED"
                                : retention.data.enabled
                                  ? "BACKUP LOCK"
                                  : "SAFE MODE · DISABLED"}
                        </span>
                    ) : null}
                </div>
                {retention.data ? (
                    <div className="mt-4 grid gap-3 text-xs text-slate-500 md:grid-cols-3">
                        <p>
                            기준 시각: {formatKoreanDateTime(retention.data.cutoff)}
                        </p>
                        <p>스케줄(UTC): {retention.data.cron}</p>
                        <p>
                            {retention.data.enabled
                                ? retention.data.archiveConfirmed
                                    ? "백업 확인과 스케줄 정리가 활성화되어 있습니다."
                                    : "정리는 활성화됐지만 백업 확인이 없어 실행되지 않습니다."
                                : "현재는 Dry-run 조회만 수행되며 데이터가 삭제되지 않습니다."}
                        </p>
                    </div>
                ) : null}
                {retention.error ? (
                    <p className="mt-3 text-sm text-red-700">{retention.error}</p>
                ) : null}
            </section>

            <form
                action="/audit-logs"
                className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm md:grid-cols-2 xl:grid-cols-4"
            >
                <label className="text-sm font-medium text-slate-700">
                    작업
                    <select
                        name="action"
                        defaultValue={parsed.values.action}
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                    >
                        <option value="">전체 작업</option>
                        {AUDIT_ACTIONS.map((action) => (
                            <option key={action} value={action}>
                                {ACTION_LABELS[action]}
                            </option>
                        ))}
                    </select>
                </label>

                <label className="text-sm font-medium text-slate-700">
                    대상 유형
                    <select
                        name="entityType"
                        defaultValue={parsed.values.entityType}
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                    >
                        <option value="">전체 대상</option>
                        {AUDIT_ENTITY_TYPES.map((entityType) => (
                            <option key={entityType} value={entityType}>
                                {ENTITY_LABELS[entityType]}
                            </option>
                        ))}
                    </select>
                </label>

                <label className="text-sm font-medium text-slate-700">
                    대상 ID
                    <input
                        name="entityId"
                        defaultValue={parsed.values.entityId}
                        maxLength={100}
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                    />
                </label>

                <label className="text-sm font-medium text-slate-700">
                    처리자
                    <input
                        name="actor"
                        defaultValue={parsed.values.actor}
                        maxLength={100}
                        placeholder="local-operator"
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                    />
                </label>

                <label className="text-sm font-medium text-slate-700">
                    시작일
                    <input
                        type="date"
                        name="from"
                        defaultValue={parsed.values.from}
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                    />
                </label>

                <label className="text-sm font-medium text-slate-700">
                    종료일
                    <input
                        type="date"
                        name="to"
                        defaultValue={parsed.values.to}
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                    />
                </label>

                <label className="text-sm font-medium text-slate-700">
                    페이지당 개수
                    <select
                        name="size"
                        defaultValue={parsed.values.size}
                        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2"
                    >
                        {[20, 30, 50, 100].map((size) => (
                            <option key={size} value={size}>
                                {size}개
                            </option>
                        ))}
                    </select>
                </label>

                <div className="flex items-end gap-2">
                    <button
                        type="submit"
                        className="rounded-lg bg-slate-950 px-5 py-2 font-semibold text-white hover:bg-slate-800"
                    >
                        조회
                    </button>
                    <Link
                        href="/audit-logs"
                        className="rounded-lg border border-slate-300 px-5 py-2 font-semibold text-slate-700 hover:bg-slate-50"
                    >
                        초기화
                    </Link>
                    <AuditExportLink href={exportHref(parsed.values)} />
                </div>
            </form>

            {result.error ? (
                <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
                    {result.error}
                </div>
            ) : null}

            <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
                    <h2 className="font-bold text-slate-900">감사 기록</h2>
                    <p className="text-sm text-slate-500">
                        총 {data?.totalElements ?? 0}건
                    </p>
                </div>

                <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-slate-200 text-sm">
                        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                            <tr>
                                <th className="px-4 py-3">시각</th>
                                <th className="px-4 py-3">처리자</th>
                                <th className="px-4 py-3">작업</th>
                                <th className="px-4 py-3">대상</th>
                                <th className="px-4 py-3">내용</th>
                                <th className="px-4 py-3">요청</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {data?.content.map((item) => (
                                <tr key={item.id} className="align-top hover:bg-slate-50">
                                    <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                                        {formatKoreanDateTime(item.occurredAt)}
                                    </td>
                                    <td className="px-4 py-3 font-medium text-slate-900">
                                        {item.actor}
                                    </td>
                                    <td className="px-4 py-3">
                                        <span className="rounded-full bg-sky-100 px-2.5 py-1 text-xs font-semibold text-sky-800">
                                            {ACTION_LABELS[item.action]}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 text-slate-700">
                                        <p>{ENTITY_LABELS[item.entityType]}</p>
                                        <p className="mt-1 font-mono text-xs text-slate-500">
                                            {item.entityId}
                                        </p>
                                    </td>
                                    <td className="max-w-md px-4 py-3 text-slate-700">
                                        <p className="font-medium">{item.summary}</p>
                                        <p className="mt-1 break-all font-mono text-xs text-slate-500">
                                            {formatDetails(item.detailsJson)}
                                        </p>
                                    </td>
                                    <td className="max-w-xs px-4 py-3 text-xs text-slate-500">
                                        <p>{item.requestMethod ?? "SYSTEM"}</p>
                                        <p className="mt-1 break-all">{item.requestPath ?? "-"}</p>
                                        <p className="mt-1 break-all font-mono">{item.traceId}</p>
                                    </td>
                                </tr>
                            ))}
                            {data && data.content.length === 0 ? (
                                <tr>
                                    <td colSpan={6} className="px-5 py-12 text-center text-slate-500">
                                        조건에 맞는 감사 로그가 없습니다.
                                    </td>
                                </tr>
                            ) : null}
                        </tbody>
                    </table>
                </div>

                {data ? (
                    <div className="flex items-center justify-between border-t border-slate-200 px-5 py-4">
                        <p className="text-sm text-slate-500">
                            {data.totalPages === 0 ? 0 : data.page + 1} / {data.totalPages} 페이지
                        </p>
                        <div className="flex gap-2">
                            {!data.first ? (
                                <Link
                                    href={pageHref(parsed.values, data.page - 1)}
                                    className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                                >
                                    이전
                                </Link>
                            ) : null}
                            {!data.last ? (
                                <Link
                                    href={pageHref(parsed.values, data.page + 1)}
                                    className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                                >
                                    다음
                                </Link>
                            ) : null}
                        </div>
                    </div>
                ) : null}
            </section>
        </div>
    );
}
