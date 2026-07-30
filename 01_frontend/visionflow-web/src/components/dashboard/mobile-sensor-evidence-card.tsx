import Link from "next/link";

import type { MobileEvidenceStatus } from "@/types/mobile-evidence-status";

interface MobileSensorEvidenceCardProps {
    status: MobileEvidenceStatus;
}

interface MetricTileProps {
    label: string;
    value: string;
    description: string;
}

function MetricTile({ label, value, description }: MetricTileProps) {
    return (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                {label}
            </div>
            <div className="mt-2 text-2xl font-bold tabular-nums text-slate-950">
                {value}
            </div>
            <div className="mt-1 text-xs text-slate-500">{description}</div>
        </div>
    );
}

function formatKoreanDateTime(value: string): string {
    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return "-";
    }

    return new Intl.DateTimeFormat("ko-KR", {
        dateStyle: "medium",
        timeStyle: "medium",
        timeZone: "Asia/Seoul",
    }).format(date);
}

function formatDuration(totalSeconds: number): string {
    const safeSeconds = Math.max(0, Math.round(totalSeconds));
    const minutes = Math.floor(safeSeconds / 60);
    const seconds = safeSeconds % 60;

    return minutes > 0 ? `${minutes}분 ${seconds}초` : `${seconds}초`;
}

function unavailablePresentation(status: MobileEvidenceStatus) {
    if (status.integrity === "FAILED") {
        return {
            label: "무결성 실패",
            badgeClassName: "bg-rose-100 text-rose-800",
            panelClassName: "border-rose-200 bg-rose-50 text-rose-900",
        };
    }

    return {
        label: "증적 없음",
        badgeClassName: "bg-slate-100 text-slate-700",
        panelClassName: "border-slate-200 bg-slate-50 text-slate-700",
    };
}

export function MobileSensorEvidenceCard({
    status,
}: MobileSensorEvidenceCardProps) {
    if (!status.available) {
        const presentation = unavailablePresentation(status);

        return (
            <section
                className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm"
                data-testid="mobile-sensor-evidence-card"
            >
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                        <div className="flex flex-wrap items-center gap-2">
                            <h2 className="text-xl font-bold text-slate-950">
                                스마트폰 실센서 E2E 증적
                            </h2>
                            <span
                                className={`rounded-full px-3 py-1 text-xs font-bold ${presentation.badgeClassName}`}
                            >
                                {presentation.label}
                            </span>
                        </div>
                        <p className="mt-2 text-sm text-slate-500">
                            GPS·방향 센서 텔레메트리와 AI 연계 검증 결과를
                            개인정보 없이 요약합니다.
                        </p>
                    </div>
                    <Link
                        href="/dashboard"
                        className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50"
                    >
                        다시 확인
                    </Link>
                </div>

                <div
                    className={`mt-5 rounded-2xl border p-4 text-sm ${presentation.panelClassName}`}
                >
                    {status.message}
                </div>
            </section>
        );
    }

    const passed = status.status === "SMARTPHONE_E2E_PASS";
    const fresh = status.freshness === "FRESH";
    const badgeLabel = passed
        ? fresh
            ? "검증 통과"
            : "통과 · 갱신 필요"
        : "검증 차단";
    const badgeClassName = passed
        ? fresh
            ? "bg-emerald-100 text-emerald-800"
            : "bg-amber-100 text-amber-800"
        : "bg-rose-100 text-rose-800";

    return (
        <section
            className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm"
            data-testid="mobile-sensor-evidence-card"
        >
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-xl font-bold text-slate-950">
                            스마트폰 실센서 E2E 증적
                        </h2>
                        <span
                            className={`rounded-full px-3 py-1 text-xs font-bold ${badgeClassName}`}
                        >
                            {badgeLabel}
                        </span>
                        <span className="rounded-full bg-sky-100 px-3 py-1 text-xs font-bold text-sky-800">
                            SHA-256 검증됨
                        </span>
                    </div>
                    <p className="mt-2 text-sm text-slate-500">
                        최신 증적의 비민감 요약입니다. 정확한 좌표, 장치 ID,
                        인증 키와 원본 영상은 표시하지 않습니다.
                    </p>
                </div>
                <div className="flex gap-2">
                    <Link
                        href="/api/mobile/evidence/status"
                        className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-700 hover:bg-slate-50"
                    >
                        요약 API
                    </Link>
                    <Link
                        href="/dashboard"
                        className="rounded-lg bg-slate-950 px-3 py-2 text-sm font-bold text-white hover:bg-slate-800"
                    >
                        새로고침
                    </Link>
                </div>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <MetricTile
                    label="원본 텔레메트리"
                    value={`${status.evidence.telemetryCount.toLocaleString("ko-KR")}회`}
                    description="세션 전체 저장 건수"
                />
                <MetricTile
                    label="MOBILE_SENSOR"
                    value={`${status.evidence.mobileSensorCount.toLocaleString("ko-KR")}회`}
                    description="스마트폰 실센서 출처"
                />
                <MetricTile
                    label="GPS · 방향"
                    value={`${status.evidence.gpsValueCount.toLocaleString("ko-KR")} · ${status.evidence.orientationValueCount.toLocaleString("ko-KR")}`}
                    description="좌표값 · 방향값 건수"
                />
                <MetricTile
                    label="AI 탐지"
                    value={`${status.evidence.detectionCount.toLocaleString("ko-KR")}개`}
                    description={`AI 이벤트 ${status.evidence.aiEventCount.toLocaleString("ko-KR")}건`}
                />
            </div>

            <div className="mt-5 grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-xl border border-slate-200 p-4">
                    <div className="text-xs font-semibold text-slate-500">
                        연결 드론
                    </div>
                    <div className="mt-1 font-bold text-slate-950">
                        드론 #{status.evidence.droneId}
                    </div>
                </div>
                <div className="rounded-xl border border-slate-200 p-4">
                    <div className="text-xs font-semibold text-slate-500">
                        비행 세션
                    </div>
                    <div className="mt-1 font-mono font-bold text-slate-950">
                        {status.evidence.sessionIdMasked}
                    </div>
                </div>
                <div className="rounded-xl border border-slate-200 p-4">
                    <div className="text-xs font-semibold text-slate-500">
                        세션 상태 · 길이
                    </div>
                    <div className="mt-1 font-bold text-slate-950">
                        {status.evidence.sessionStatus} ·{" "}
                        {formatDuration(status.evidence.durationSeconds)}
                    </div>
                </div>
                <div className="rounded-xl border border-slate-200 p-4">
                    <div className="text-xs font-semibold text-slate-500">
                        증적 생성
                    </div>
                    <div className="mt-1 font-bold text-slate-950">
                        {formatKoreanDateTime(status.generatedAt)}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                        {status.ageHours.toLocaleString("ko-KR")}시간 전
                    </div>
                </div>
            </div>

            <div className="mt-5 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs text-emerald-900">
                <span>
                    개인정보 보호 표식 확인 · 장치 ID{" "}
                    {status.evidence.sourceDeviceIdRecorded
                        ? "기록됨"
                        : "미기록"}
                </span>
                <span className="font-mono">
                    SHA-256 {status.checksumSha256.slice(0, 12)}…
                </span>
            </div>
        </section>
    );
}
