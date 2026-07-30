"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";

import { useOperatorAccess } from "@/components/security/operator-access-provider";
import {
    parseDemoScenario,
    type DemoScenario,
    type DemoScenarioStage,
} from "@/types/demo-scenario";
import {
    parseMaintenanceFlightClearance,
    type MaintenanceFlightClearance,
} from "@/types/maintenance-flight-clearance";

type ScenarioAction = "detect" | "escalate" | "resolve" | "complete";

const STEPS: Array<{
    stage: DemoScenarioStage;
    title: string;
    description: string;
}> = [
    {
        stage: "READY",
        title: "1. 비행 준비",
        description: "세션 생성 · 텔레메트리 경로 저장",
    },
    {
        stage: "DETECTED",
        title: "2. AI 화재 탐지",
        description: "추론 이벤트 · 경보 · Incident 생성",
    },
    {
        stage: "ESCALATED",
        title: "3. SLA 에스컬레이션",
        description: "대응 기한 초과 · 에스컬레이션 Lv.1",
    },
    {
        stage: "RESOLVED",
        title: "4. 관제 처리",
        description: "AI 경보와 Incident 동시 해결",
    },
    {
        stage: "COMPLETED",
        title: "5. 비행 종료",
        description: "세션 종료 · 보고서 확인",
    },
];

const ACTION_BY_STAGE: Partial<
    Record<DemoScenarioStage, ScenarioAction>
> = {
    READY: "detect",
    DETECTED: "escalate",
    ESCALATED: "resolve",
    RESOLVED: "complete",
};

const ACTION_LABEL: Record<ScenarioAction, string> = {
    detect: "AI 화재 탐지 실행",
    escalate: "SLA 초과 처리 실행",
    resolve: "관제 해결 처리",
    complete: "비행 세션 종료",
};

function extractMessage(value: unknown, fallback: string): string {
    if (
        typeof value === "object" &&
        value !== null &&
        "message" in value &&
        typeof value.message === "string"
    ) {
        return value.message;
    }
    return fallback;
}

function formatTime(value: string | null): string {
    if (!value) {
        return "-";
    }

    const timestamp = Date.parse(value);
    return Number.isFinite(timestamp)
        ? new Intl.DateTimeFormat("ko-KR", {
              dateStyle: "medium",
              timeStyle: "medium",
          }).format(timestamp)
        : value;
}

function buildControlHref(scenario: DemoScenario): string {
    const context = scenario.incidentContext;
    const params = new URLSearchParams({
        droneId: String(scenario.droneId),
    });

    if (!context || scenario.incidentId === null) {
        return `/drones?${params.toString()}`;
    }

    params.set("incidentId", String(scenario.incidentId));
    params.set("incidentAt", context.occurredAt);
    params.set("incidentSource", "AI_ALERT");
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

async function readScenarioResponse(
    response: Response,
    fallback: string,
): Promise<DemoScenario> {
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
        const configurationHint =
            response.status === 404
                ? " 백엔드에서 VISIONFLOW_DEMO_ENABLED=true 설정을 확인해 주세요."
                : "";
        throw new Error(extractMessage(body, fallback) + configurationHint);
    }

    const parsed = parseDemoScenario(body);
    if (!parsed) {
        throw new Error("시연 API 응답 형식을 해석할 수 없습니다.");
    }
    return parsed;
}

async function startScenarioRequest(
    droneId: number,
    latitude: number,
    longitude: number,
): Promise<DemoScenario> {
    const response = await fetch("/api/demo/scenarios", {
        method: "POST",
        cache: "no-store",
        headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
        },
        body: JSON.stringify({ droneId, latitude, longitude }),
    });
    return readScenarioResponse(response, "시연 시나리오를 시작하지 못했습니다.");
}

async function runScenarioAction(
    scenarioId: string,
    action: ScenarioAction,
): Promise<DemoScenario> {
    const response = await fetch(
        `/api/demo/scenarios/${encodeURIComponent(scenarioId)}/${action}`,
        {
            method: "POST",
            cache: "no-store",
            headers: { Accept: "application/json" },
        },
    );
    return readScenarioResponse(
        response,
        `${ACTION_LABEL[action]}에 실패했습니다.`,
    );
}

function wait(milliseconds: number): Promise<void> {
    return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

export function DemoScenarioConsole() {
    const { canOperate, operateDeniedReason } = useOperatorAccess();
    const [droneIdText, setDroneIdText] = useState("1");
    const [latitudeText, setLatitudeText] = useState("37.5665");
    const [longitudeText, setLongitudeText] = useState("126.9780");
    const [scenario, setScenario] = useState<DemoScenario | null>(null);
    const [busy, setBusy] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [logs, setLogs] = useState<string[]>([]);
    const [flightClearance, setFlightClearance] =
        useState<MaintenanceFlightClearance | null>(null);
    const [clearanceError, setClearanceError] = useState<string | null>(null);

    function inputValues() {
        const droneId = Number(droneIdText);
        const latitude = Number(latitudeText);
        const longitude = Number(longitudeText);

        if (!Number.isInteger(droneId) || droneId < 1) {
            throw new Error("드론 ID는 1 이상의 정수여야 합니다.");
        }
        if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90) {
            throw new Error("위도는 -90~90 범위여야 합니다.");
        }
        if (
            !Number.isFinite(longitude) ||
            longitude < -180 ||
            longitude > 180
        ) {
            throw new Error("경도는 -180~180 범위여야 합니다.");
        }
        return { droneId, latitude, longitude };
    }

    function addLog(message: string) {
        setLogs((current) => [
            `${new Date().toLocaleTimeString("ko-KR")} · ${message}`,
            ...current,
        ]);
    }

    async function requireFlightClearance(
        droneId: number,
    ): Promise<MaintenanceFlightClearance> {
        const response = await fetch(
            `/api/maintenance/flight-clearance/${droneId}`,
            {
                method: "GET",
                headers: { Accept: "application/json" },
                cache: "no-store",
            },
        );
        if (!response.ok) {
            const body: unknown = await response.json().catch(() => null);
            throw new Error(
                extractMessage(
                    body,
                    `사전 비행 허가 조회 실패: HTTP ${response.status}`,
                ),
            );
        }

        const parsed = parseMaintenanceFlightClearance(
            await response.json() as unknown,
        );
        if (!parsed || parsed.droneId !== droneId) {
            throw new Error("사전 비행 허가 응답 형식이 올바르지 않습니다.");
        }

        setFlightClearance(parsed);
        setClearanceError(null);
        if (!parsed.flightAllowed) {
            throw new Error(parsed.reason);
        }
        return parsed;
    }

    async function checkPreflight() {
        setBusy("preflight");
        setClearanceError(null);
        try {
            const { droneId } = inputValues();
            const clearance = await requireFlightClearance(droneId);
            addLog(
                clearance.attentionRequired
                    ? `Drone #${droneId} 사전 점검 주의 후 시작 가능`
                    : `Drone #${droneId} 사전 비행 허가 확인`,
            );
        } catch (caught) {
            setClearanceError(
                caught instanceof Error
                    ? caught.message
                    : "사전 비행 허가를 확인하지 못했습니다.",
            );
        } finally {
            setBusy(null);
        }
    }

    async function startScenario(): Promise<DemoScenario | null> {
        if (!canOperate) {
            setError(operateDeniedReason);
            return null;
        }

        setBusy("start");
        setError(null);
        try {
            const values = inputValues();
            await requireFlightClearance(values.droneId);
            const next = await startScenarioRequest(
                values.droneId,
                values.latitude,
                values.longitude,
            );
            setScenario(next);
            setLogs([]);
            addLog(next.lastMessage);
            return next;
        } catch (caught) {
            setError(
                caught instanceof Error
                    ? caught.message
                    : "시연 시나리오 시작에 실패했습니다.",
            );
            return null;
        } finally {
            setBusy(null);
        }
    }

    async function executeAction(action: ScenarioAction) {
        if (!scenario) {
            return;
        }

        if (!canOperate) {
            setError(operateDeniedReason);
            return;
        }

        setBusy(action);
        setError(null);
        try {
            const next = await runScenarioAction(scenario.scenarioId, action);
            setScenario(next);
            addLog(next.lastMessage);
        } catch (caught) {
            setError(
                caught instanceof Error
                    ? caught.message
                    : `${ACTION_LABEL[action]}에 실패했습니다.`,
            );
        } finally {
            setBusy(null);
        }
    }

    async function runAll() {
        if (!canOperate) {
            setError(operateDeniedReason);
            return;
        }

        setBusy("auto");
        setError(null);

        try {
            let current = scenario;
            if (!current || current.stage === "COMPLETED") {
                const values = inputValues();
                await requireFlightClearance(values.droneId);
                current = await startScenarioRequest(
                    values.droneId,
                    values.latitude,
                    values.longitude,
                );
                setScenario(current);
                setLogs([]);
                addLog(current.lastMessage);
                await wait(700);
            }

            while (current.stage !== "COMPLETED") {
                const action = ACTION_BY_STAGE[current.stage];
                if (!action) {
                    throw new Error("다음 시연 단계를 결정할 수 없습니다.");
                }

                current = await runScenarioAction(
                    current.scenarioId,
                    action,
                );
                setScenario(current);
                addLog(current.lastMessage);
                if (current.stage !== "COMPLETED") {
                    await wait(900);
                }
            }
        } catch (caught) {
            setError(
                caught instanceof Error
                    ? caught.message
                    : "전체 시연 자동 실행에 실패했습니다.",
            );
        } finally {
            setBusy(null);
        }
    }

    const currentStageIndex = scenario
        ? STEPS.findIndex((step) => step.stage === scenario.stage)
        : -1;
    const nextAction = scenario ? ACTION_BY_STAGE[scenario.stage] : undefined;
    const context = scenario?.incidentContext ?? null;
    const inputDroneId = /^\d+$/.test(droneIdText.trim())
        ? Number(droneIdText)
        : null;
    const currentFlightClearance =
        inputDroneId !== null && flightClearance?.droneId === inputDroneId
            ? flightClearance
            : null;
    const flightGateBlocked =
        currentFlightClearance !== null &&
        !currentFlightClearance.flightAllowed;

    return (
        <main className="min-h-screen bg-slate-950 px-5 py-8 text-slate-100 lg:px-10">
            <div className="mx-auto max-w-7xl space-y-6">
                <header className="flex flex-col gap-4 rounded-3xl border border-slate-800 bg-slate-900/80 p-6 shadow-2xl lg:flex-row lg:items-center lg:justify-between">
                    <div>
                        <p className="text-sm font-semibold tracking-[0.24em] text-cyan-400">
                            VISIONFLOW PRESENTATION MODE
                        </p>
                        <h1 className="mt-2 text-3xl font-bold">
                            스마트 드론 통합 시연 콘솔
                        </h1>
                        <p className="mt-2 text-sm text-slate-400">
                            가상 비행부터 AI 화재 탐지, SLA 상향, 관제 처리와
                            보고서까지 한 흐름으로 재현합니다.
                        </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                        <Link
                            href="/dashboard"
                            className="rounded-xl border border-slate-700 px-4 py-2 text-sm font-semibold hover:bg-slate-800"
                        >
                            관제 대시보드
                        </Link>
                        <Link
                            href="/drones"
                            className="rounded-xl bg-cyan-500 px-4 py-2 text-sm font-bold text-slate-950 hover:bg-cyan-400"
                        >
                            실시간 드론 관제
                        </Link>
                    </div>
                </header>

                <section className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
                    <div className="rounded-3xl border border-slate-800 bg-slate-900 p-6">
                        <h2 className="text-lg font-bold">시연 설정</h2>
                        <div className="mt-5 space-y-4">
                            <label className="block text-sm text-slate-300">
                                드론 ID
                                <input
                                    value={droneIdText}
                                    onChange={(event) => {
                                        setDroneIdText(event.target.value);
                                        setFlightClearance(null);
                                        setClearanceError(null);
                                    }}
                                    disabled={busy !== null}
                                    inputMode="numeric"
                                    className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 outline-none focus:border-cyan-400"
                                />
                            </label>
                            <div className="grid grid-cols-2 gap-3">
                                <label className="block text-sm text-slate-300">
                                    시작 위도
                                    <input
                                        value={latitudeText}
                                        onChange={(event) =>
                                            setLatitudeText(event.target.value)
                                        }
                                        disabled={busy !== null}
                                        inputMode="decimal"
                                        className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 outline-none focus:border-cyan-400"
                                    />
                                </label>
                                <label className="block text-sm text-slate-300">
                                    시작 경도
                                    <input
                                        value={longitudeText}
                                        onChange={(event) =>
                                            setLongitudeText(event.target.value)
                                        }
                                        disabled={busy !== null}
                                        inputMode="decimal"
                                        className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2.5 outline-none focus:border-cyan-400"
                                    />
                                </label>
                            </div>
                        </div>

                        <div
                            className={`mt-5 rounded-2xl border p-4 ${
                                flightGateBlocked
                                    ? "border-red-500/70 bg-red-500/10"
                                    : currentFlightClearance?.attentionRequired
                                      ? "border-amber-400/60 bg-amber-400/10"
                                      : currentFlightClearance
                                        ? "border-emerald-500/60 bg-emerald-500/10"
                                        : "border-slate-700 bg-slate-950/60"
                            }`}
                        >
                            <div className="flex flex-wrap items-start justify-between gap-3">
                                <div>
                                    <p className="text-xs font-black uppercase tracking-wider text-slate-400">
                                        사전 비행 허가
                                    </p>
                                    <p className="mt-1 font-black">
                                        {!currentFlightClearance
                                            ? "확인 대기"
                                            : flightGateBlocked
                                              ? "시연 시작 차단"
                                              : currentFlightClearance.attentionRequired
                                                ? "주의 후 시작 가능"
                                                : "시연 시작 가능"}
                                    </p>
                                    <p className="mt-1 text-xs leading-5 text-slate-400">
                                        {currentFlightClearance?.reason ??
                                            "시연 시작 전에 최신 정비 작업과 재운항 승인 상태를 확인합니다."}
                                    </p>
                                </div>
                                <button
                                    type="button"
                                    onClick={() => void checkPreflight()}
                                    disabled={busy !== null}
                                    className="rounded-lg border border-slate-600 px-3 py-2 text-xs font-bold hover:bg-slate-800 disabled:opacity-50"
                                >
                                    {busy === "preflight"
                                        ? "확인 중..."
                                        : "비행 허가 확인"}
                                </button>
                            </div>
                            {clearanceError && (
                                <p className="mt-3 rounded-lg bg-red-950/60 p-3 text-xs font-bold text-red-200">
                                    {clearanceError}
                                </p>
                            )}
                            {currentFlightClearance?.workOrderId !== null &&
                                currentFlightClearance?.workOrderId !==
                                    undefined && (
                                    <Link
                                        href={
                                            `/maintenance?droneId=${currentFlightClearance.droneId}` +
                                            `&workOrderId=${currentFlightClearance.workOrderId}`
                                        }
                                        className="mt-3 inline-flex rounded-lg bg-white px-3 py-2 text-xs font-black text-slate-950"
                                    >
                                        점검 작업 #
                                        {currentFlightClearance.workOrderId} 열기
                                    </Link>
                                )}
                        </div>

                        <button
                            type="button"
                            onClick={() => void runAll()}
                            disabled={
                                busy !== null ||
                                !canOperate ||
                                flightGateBlocked
                            }
                            title={canOperate ? undefined : operateDeniedReason ?? undefined}
                            className="mt-6 w-full rounded-xl bg-gradient-to-r from-cyan-400 to-blue-500 px-4 py-3 font-black text-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            {busy === "auto"
                                ? "전체 시연 실행 중..."
                                : "전체 시연 자동 실행"}
                        </button>
                        <button
                            type="button"
                            onClick={() => void startScenario()}
                            disabled={
                                busy !== null ||
                                !canOperate ||
                                flightGateBlocked ||
                                (scenario !== null &&
                                    scenario.stage !== "COMPLETED")
                            }
                            className="mt-3 w-full rounded-xl border border-slate-700 px-4 py-3 font-semibold hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            새 시연 수동 시작
                        </button>

                        <div className="mt-5 rounded-2xl bg-amber-400/10 p-4 text-xs leading-5 text-amber-200">
                            백엔드 실행 전에 환경 변수
                            <strong className="mx-1 text-amber-100">
                                VISIONFLOW_DEMO_ENABLED=true
                            </strong>
                            를 설정하세요. 실제 발표가 아닌 환경에서는 false를
                            유지합니다.
                        </div>
                    </div>

                    <div className="space-y-6">
                        <div className="grid gap-3 md:grid-cols-5">
                            {STEPS.map((step, index) => {
                                const completed = index <= currentStageIndex;
                                const active = index === currentStageIndex;
                                return (
                                    <div
                                        key={step.stage}
                                        className={`rounded-2xl border p-4 transition ${
                                            active
                                                ? "border-cyan-400 bg-cyan-400/10"
                                                : completed
                                                  ? "border-emerald-700 bg-emerald-500/10"
                                                  : "border-slate-800 bg-slate-900"
                                        }`}
                                    >
                                        <p
                                            className={`text-sm font-bold ${
                                                completed
                                                    ? "text-emerald-300"
                                                    : "text-slate-300"
                                            }`}
                                        >
                                            {step.title}
                                        </p>
                                        <p className="mt-2 text-xs leading-5 text-slate-500">
                                            {step.description}
                                        </p>
                                    </div>
                                );
                            })}
                        </div>

                        <div className="rounded-3xl border border-slate-800 bg-slate-900 p-6">
                            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                                <div>
                                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                                        현재 상태
                                    </p>
                                    <p className="mt-2 text-xl font-bold text-cyan-300">
                                        {scenario?.stage ?? "NOT_STARTED"}
                                    </p>
                                    <p className="mt-2 text-sm text-slate-400">
                                        {scenario?.lastMessage ??
                                            "시연을 시작하면 진행 상황이 표시됩니다."}
                                    </p>
                                </div>
                                {nextAction ? (
                                    <button
                                        type="button"
                                        onClick={() =>
                                            void executeAction(nextAction)
                                        }
                                        disabled={busy !== null || !canOperate}
                                        title={canOperate ? undefined : operateDeniedReason ?? undefined}
                                        className="rounded-xl bg-rose-500 px-5 py-3 font-bold text-white hover:bg-rose-400 disabled:opacity-50"
                                    >
                                        {busy === nextAction
                                            ? "처리 중..."
                                            : ACTION_LABEL[nextAction]}
                                    </button>
                                ) : null}
                            </div>

                            {error ? (
                                <div className="mt-5 rounded-xl border border-red-500/60 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                                    {error}
                                </div>
                            ) : null}

                            {scenario ? (
                                <dl className="mt-6 grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
                                    <div className="rounded-xl bg-slate-950 p-3">
                                        <dt className="text-slate-500">시나리오 ID</dt>
                                        <dd className="mt-1 truncate font-mono text-xs">
                                            {scenario.scenarioId}
                                        </dd>
                                    </div>
                                    <div className="rounded-xl bg-slate-950 p-3">
                                        <dt className="text-slate-500">비행 세션</dt>
                                        <dd className="mt-1 truncate font-mono text-xs">
                                            {scenario.flightSessionId}
                                        </dd>
                                    </div>
                                    <div className="rounded-xl bg-slate-950 p-3">
                                        <dt className="text-slate-500">Incident</dt>
                                        <dd className="mt-1 font-semibold">
                                            {scenario.incidentId ?? "-"}
                                        </dd>
                                    </div>
                                    <div className="rounded-xl bg-slate-950 p-3">
                                        <dt className="text-slate-500">마지막 갱신</dt>
                                        <dd className="mt-1 text-xs">
                                            {formatTime(scenario.updatedAt)}
                                        </dd>
                                    </div>
                                </dl>
                            ) : null}
                        </div>

                        {scenario && context ? (
                            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
                                <div className="rounded-3xl border border-slate-800 bg-slate-900 p-6">
                                    <h2 className="text-lg font-bold">
                                        관제 증거 바로가기
                                    </h2>
                                    <p className="mt-2 text-sm text-slate-400">
                                        탐지 시각 인접 좌표와 저장된 경로를 관제
                                        지도에서 재생합니다.
                                    </p>
                                    <div className="mt-5 flex flex-wrap gap-3">
                                        <Link
                                            href={buildControlHref(scenario)}
                                            className="rounded-xl bg-cyan-500 px-4 py-2.5 font-bold text-slate-950 hover:bg-cyan-400"
                                        >
                                            관제 지도에서 보기
                                        </Link>
                                        {scenario.incidentId !== null ? (
                                            <Link
                                                href={`/incidents/${scenario.incidentId}/report`}
                                                className="rounded-xl border border-slate-700 px-4 py-2.5 font-semibold hover:bg-slate-800"
                                            >
                                                Incident 보고서
                                            </Link>
                                        ) : null}
                                    </div>
                                    <dl className="mt-5 grid grid-cols-2 gap-3 text-sm">
                                        <div className="rounded-xl bg-slate-950 p-3">
                                            <dt className="text-slate-500">위도</dt>
                                            <dd className="mt-1">
                                                {context.latitude ?? "-"}
                                            </dd>
                                        </div>
                                        <div className="rounded-xl bg-slate-950 p-3">
                                            <dt className="text-slate-500">경도</dt>
                                            <dd className="mt-1">
                                                {context.longitude ?? "-"}
                                            </dd>
                                        </div>
                                    </dl>
                                </div>
                                <div className="overflow-hidden rounded-3xl border border-slate-800 bg-slate-900">
                                    {context.snapshotAvailable &&
                                    context.snapshotUrl ? (
                                        <Image
                                            src={context.snapshotUrl}
                                            alt="AI 화재 탐지 시연 스냅샷"
                                            width={960}
                                            height={540}
                                            unoptimized
                                            className="h-full min-h-56 w-full object-cover"
                                        />
                                    ) : (
                                        <div className="flex min-h-56 items-center justify-center p-6 text-sm text-slate-500">
                                            AI 탐지 후 스냅샷이 표시됩니다.
                                        </div>
                                    )}
                                </div>
                            </div>
                        ) : null}

                        <div className="rounded-3xl border border-slate-800 bg-slate-900 p-6">
                            <h2 className="text-lg font-bold">시연 로그</h2>
                            <div className="mt-4 min-h-24 space-y-2 font-mono text-xs text-slate-400">
                                {logs.length > 0 ? (
                                    logs.map((log, index) => (
                                        <p key={`${log}-${index}`}>{log}</p>
                                    ))
                                ) : (
                                    <p>아직 실행된 단계가 없습니다.</p>
                                )}
                            </div>
                        </div>
                    </div>
                </section>
            </div>
        </main>
    );
}
