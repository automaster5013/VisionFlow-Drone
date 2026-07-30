"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
    parseIncidentReport,
    type IncidentReport,
} from "@/types/incident-report";
import type {
    IncidentActionType,
    IncidentPriority,
    IncidentStatus,
} from "@/types/incident";

interface IncidentReportViewProps {
    incidentId: number;
}

function formatDateTime(value: string | null): string {
    if (!value) {
        return "-";
    }

    const normalized = value.replace(
        /(\.\d{3})\d+(?=Z|[+-]\d{2}:\d{2}|$)/,
        "$1",
    );
    const date = new Date(normalized);

    return Number.isNaN(date.getTime())
        ? value
        : date.toLocaleString("ko-KR");
}

function formatDuration(value: number | null): string {
    if (value === null) {
        return "미처리";
    }

    const seconds = Math.max(0, Math.round(value));
    const hours = Math.floor(seconds / 3_600);
    const minutes = Math.floor((seconds % 3_600) / 60);
    const remainingSeconds = seconds % 60;

    if (hours > 0) {
        return `${hours}시간 ${minutes}분 ${remainingSeconds}초`;
    }
    if (minutes > 0) {
        return `${minutes}분 ${remainingSeconds}초`;
    }

    return `${remainingSeconds}초`;
}

function priorityLabel(priority: IncidentPriority): string {
    return {
        LOW: "낮음",
        MEDIUM: "보통",
        HIGH: "높음",
        CRITICAL: "긴급",
    }[priority];
}

function statusLabel(status: IncidentStatus): string {
    return {
        OPEN: "접수",
        IN_PROGRESS: "처리 중",
        RESOLVED: "해결",
        CLOSED: "종료",
    }[status];
}

function actionLabel(actionType: IncidentActionType): string {
    return {
        CREATED: "Incident 생성",
        ASSIGNED: "담당자 지정",
        PRIORITY_CHANGED: "우선순위 변경",
        STATUS_CHANGED: "상태 변경",
        NOTE_ADDED: "조치 메모",
        SOURCE_SYNCHRONIZED: "원본 상태 동기화",
        SLA_ESCALATED: "SLA 자동 에스컬레이션",
    }[actionType];
}

function reportSlaLabel(report: IncidentReport): string {
    const { incident } = report;

    if (incident.slaBreachedAt) {
        return `기한 초과 · 자동 에스컬레이션 ${incident.escalationLevel}회`;
    }

    if (incident.status === "RESOLVED" || incident.status === "CLOSED") {
        return "SLA 기한 내 처리";
    }

    return incident.slaDueAt
        ? `진행 중 · ${formatDateTime(incident.slaDueAt)}까지`
        : "SLA 기한 없음";
}

function locationLabel(report: IncidentReport): string {
    return {
        GEOFENCE_EVENT: "지오펜스 최초 위반 좌표",
        NEAREST_TELEMETRY: "발생 시각 인접 텔레메트리",
        UNAVAILABLE: "확보된 좌표 없음",
    }[report.context.locationSource];
}

function buildControlHref(report: IncidentReport): string {
    const { incident, context } = report;
    const params = new URLSearchParams({
        droneId: String(context.droneId),
        incidentId: String(incident.id),
        incidentAt: context.occurredAt,
        incidentSource: incident.sourceType,
    });

    if (context.replayAvailable && context.sessionId) {
        params.set("sessionId", context.sessionId);
    }
    if (context.latitude !== null && context.longitude !== null) {
        params.set("incidentLat", String(context.latitude));
        params.set("incidentLng", String(context.longitude));
    }
    if (context.altitude !== null) {
        params.set("incidentAlt", String(context.altitude));
    }

    return `/drones?${params.toString()}`;
}

function ReportValue({
    label,
    value,
}: {
    label: string;
    value: string;
}) {
    return (
        <div className="rounded-xl bg-slate-50 p-4">
            <div className="text-xs font-bold text-slate-500">{label}</div>
            <div className="mt-1 break-words text-sm font-semibold text-slate-900">
                {value}
            </div>
        </div>
    );
}

export function IncidentReportView({ incidentId }: IncidentReportViewProps) {
    const [report, setReport] = useState<IncidentReport | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const abortController = new AbortController();

        fetch(`/api/incidents/${incidentId}/report`, {
            method: "GET",
            headers: { Accept: "application/json" },
            cache: "no-store",
            signal: abortController.signal,
        })
            .then(async (response) => {
                const payload: unknown = await response.json();

                if (!response.ok) {
                    const message =
                        typeof payload === "object" &&
                        payload !== null &&
                        "message" in payload &&
                        typeof payload.message === "string"
                            ? payload.message
                            : `Incident 보고서 조회 실패: ${response.status}`;
                    throw new Error(message);
                }

                const parsed = parseIncidentReport(payload);
                if (!parsed) {
                    throw new Error("Incident 보고서 응답 형식이 올바르지 않습니다.");
                }

                setReport(parsed);
                setError(null);
            })
            .catch((loadError: unknown) => {
                if (
                    loadError instanceof DOMException &&
                    loadError.name === "AbortError"
                ) {
                    return;
                }

                setError(
                    loadError instanceof Error
                        ? loadError.message
                        : "Incident 보고서를 불러오지 못했습니다.",
                );
            })
            .finally(() => {
                if (!abortController.signal.aborted) {
                    setLoading(false);
                }
            });

        return () => abortController.abort();
    }, [incidentId]);

    const coordinateText = useMemo(() => {
        if (!report || report.context.latitude === null ||
            report.context.longitude === null) {
            return "-";
        }

        return `${report.context.latitude}, ${report.context.longitude}`;
    }, [report]);

    if (loading) {
        return (
            <main className="mx-auto max-w-5xl p-8 text-center text-slate-500">
                Incident 보고서를 작성하는 중입니다.
            </main>
        );
    }

    if (error || !report) {
        return (
            <main className="mx-auto max-w-3xl p-8">
                <div className="rounded-2xl border border-red-300 bg-red-50 p-6 text-red-900">
                    {error ?? "Incident 보고서를 표시할 수 없습니다."}
                </div>
                <Link
                    href="/dashboard"
                    className="mt-4 inline-flex rounded-lg bg-slate-900 px-4 py-2 font-bold text-white"
                >
                    Dashboard로 돌아가기
                </Link>
            </main>
        );
    }

    const { incident, context, metrics, history } = report;

    return (
        <main className="min-h-screen bg-slate-100 px-4 py-8 print:bg-white print:p-0">
            <article className="mx-auto max-w-5xl rounded-3xl bg-white p-6 shadow-sm print:max-w-none print:rounded-none print:p-6 print:shadow-none sm:p-10">
                <div className="mb-6 flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 pb-6">
                    <div>
                        <div className="text-xs font-bold uppercase tracking-[0.2em] text-sky-700">
                            VisionFlow Drone Control Center
                        </div>
                        <h1 className="mt-2 text-3xl font-black text-slate-950">
                            Incident 대응 보고서
                        </h1>
                        <p className="mt-2 text-sm text-slate-500">
                            Incident #{incident.id} · 보고서 생성 {formatDateTime(report.generatedAt)}
                        </p>
                    </div>
                    <div className="flex flex-wrap gap-2 print:hidden">
                        <Link
                            href="/dashboard"
                            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700"
                        >
                            Dashboard
                        </Link>
                        <Link
                            href={buildControlHref(report)}
                            className="rounded-lg bg-violet-700 px-4 py-2 text-sm font-bold text-white"
                        >
                            관제 증거 확인
                        </Link>
                        <button
                            type="button"
                            onClick={() => window.print()}
                            className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-bold text-white"
                        >
                            인쇄 / PDF 저장
                        </button>
                    </div>
                </div>

                <section>
                    <h2 className="text-lg font-black text-slate-950">상황 개요</h2>
                    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                        <ReportValue label="제목" value={incident.title} />
                        <ReportValue label="상태" value={statusLabel(incident.status)} />
                        <ReportValue label="우선순위" value={priorityLabel(incident.priority)} />
                        <ReportValue label="담당자" value={incident.assignee ?? "미지정"} />
                        <ReportValue label="드론" value={`#${incident.droneId}`} />
                        <ReportValue label="원본" value={`${incident.sourceType} #${incident.sourceId}`} />
                        <ReportValue label="발생 시각" value={formatDateTime(context.occurredAt)} />
                        <ReportValue label="비행 세션" value={context.sessionId ?? "-"} />
                        <ReportValue label="SLA 결과" value={reportSlaLabel(report)} />
                        <ReportValue label="SLA 기한" value={formatDateTime(incident.slaDueAt)} />
                    </div>
                    <p className="mt-4 whitespace-pre-wrap rounded-xl border border-slate-200 p-4 text-sm leading-7 text-slate-700">
                        {incident.summary}
                    </p>
                </section>

                <section className="mt-8">
                    <h2 className="text-lg font-black text-slate-950">대응 지표</h2>
                    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                        <ReportValue label="최초 대응시간" value={formatDuration(metrics.firstResponseSeconds)} />
                        <ReportValue label="해결 소요시간" value={formatDuration(metrics.resolutionSeconds)} />
                        <ReportValue label="전체 조치" value={`${metrics.actionCount}건`} />
                        <ReportValue label="조치 메모" value={`${metrics.noteCount}건`} />
                    </div>
                </section>

                <section className="mt-8 break-inside-avoid rounded-2xl border border-violet-200 bg-violet-50 p-5">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                        <div>
                            <h2 className="text-lg font-black text-violet-950">발생 증거</h2>
                            <p className="mt-1 text-sm text-violet-800">{locationLabel(report)}</p>
                        </div>
                        <span className={`rounded-full px-3 py-1 text-xs font-bold ${
                            metrics.evidenceAvailable
                                ? "bg-emerald-100 text-emerald-800"
                                : "bg-slate-200 text-slate-600"
                        }`}>
                            {metrics.evidenceAvailable ? "증거 연결됨" : "증거 없음"}
                        </span>
                    </div>
                    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                        <ReportValue label="좌표" value={coordinateText} />
                        <ReportValue label="고도" value={context.altitude === null ? "-" : `${context.altitude}m`} />
                        <ReportValue label="좌표 기록 시각" value={formatDateTime(context.locationRecordedAt)} />
                        <ReportValue label="AI 이벤트" value={context.aiEventId === null ? "-" : `#${context.aiEventId}`} />
                    </div>
                    {context.snapshotAvailable && context.snapshotUrl && (
                        <Link
                            href={context.snapshotUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-4 inline-flex rounded-lg border border-violet-300 bg-white px-4 py-2 text-sm font-bold text-violet-800 print:hidden"
                        >
                            AI 스냅샷 원본 열기
                        </Link>
                    )}
                </section>

                <section className="mt-8">
                    <h2 className="text-lg font-black text-slate-950">처리 이력</h2>
                    <div className="mt-4 space-y-3">
                        {history.map((item, index) => (
                            <div
                                key={item.id}
                                className="break-inside-avoid rounded-xl border border-slate-200 p-4"
                            >
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                    <div className="font-bold text-slate-900">
                                        {index + 1}. {actionLabel(item.actionType)}
                                    </div>
                                    <div className="text-xs text-slate-500">
                                        {formatDateTime(item.createdAt)}
                                    </div>
                                </div>
                                <div className="mt-1 text-sm text-slate-600">
                                    처리자 {item.actor}
                                    {item.previousStatus && item.newStatus
                                        ? ` · ${statusLabel(item.previousStatus)} → ${statusLabel(item.newStatus)}`
                                        : ""}
                                </div>
                                {item.note && (
                                    <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">
                                        {item.note}
                                    </p>
                                )}
                            </div>
                        ))}
                    </div>
                </section>

                <footer className="mt-10 border-t border-slate-200 pt-4 text-xs text-slate-500">
                    본 보고서는 VisionFlow Incident 데이터와 연결된 텔레메트리·AI 증거를 기준으로 자동 생성되었습니다.
                </footer>
            </article>
        </main>
    );
}
