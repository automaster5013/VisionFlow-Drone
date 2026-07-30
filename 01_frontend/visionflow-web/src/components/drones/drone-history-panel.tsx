"use client";

import { useState } from "react";

import type {
    DroneTrackPoint,
} from "@/hooks/use-drone-fleet-telemetry";
import type {
    DroneTelemetryHistory,
} from "@/types/drone-telemetry-history";

type HistoryStatus =
    | "IDLE"
    | "LOADING"
    | "SUCCESS"
    | "EMPTY"
    | "ERROR";

interface DroneHistoryPanelProps {
    droneId: number;
    currentPointCount: number;
    onHistoryLoaded: (
        points: DroneTrackPoint[],
    ) => void;
}

function toDateTimeLocal(date: Date): string {
    const timezoneOffset =
        date.getTimezoneOffset() * 60_000;

    return new Date(
        date.getTime() - timezoneOffset,
    )
        .toISOString()
        .slice(0, 16);
}

function createDefaultFrom(): string {
    return toDateTimeLocal(
        new Date(Date.now() - 60 * 60 * 1_000),
    );
}

function createDefaultTo(): string {
    return toDateTimeLocal(new Date());
}

function normalizeDateTime(value: string): string {
    return value.length === 16
        ? `${value}:00`
        : value;
}

function parseRecordedAt(value: string): number {
    const normalized = value.replace(
        /(\.\d{3})\d+(?=Z|[+-]\d{2}:\d{2}|$)/,
        "$1",
    );

    return new Date(normalized).getTime();
}

function toTrackPoint(
    history: DroneTelemetryHistory,
): DroneTrackPoint | null {
    if (
        history.latitude === null ||
        history.longitude === null
    ) {
        return null;
    }

    const latitude = Number(history.latitude);
    const longitude = Number(history.longitude);
    const receivedAt = parseRecordedAt(
        history.recordedAt,
    );

    const altitude =
        history.altitude === null
            ? null
            : Number(history.altitude);

    if (
        !Number.isFinite(latitude) ||
        !Number.isFinite(longitude) ||
        !Number.isFinite(receivedAt)
    ) {
        return null;
    }

    return {
        latitude,
        longitude,
        altitude:
            altitude !== null &&
            Number.isFinite(altitude)
                ? altitude
                : null,
        receivedAt,
    };
}

function statusText(
    status: HistoryStatus,
    count: number,
): string {
    switch (status) {
        case "LOADING":
            return "과거 경로를 불러오는 중입니다.";
        case "SUCCESS":
            return `과거 경로 ${count}개 지점을 불러왔습니다.`;
        case "EMPTY":
            return "선택한 시간 범위에 경로가 없습니다.";
        case "ERROR":
            return "과거 경로 조회에 실패했습니다.";
        default:
            return `현재 지도 경로 ${count}개 지점`;
    }
}

export function DroneHistoryPanel({
                                      droneId,
                                      currentPointCount,
                                      onHistoryLoaded,
                                  }: DroneHistoryPanelProps) {
    const [from, setFrom] = useState(
        createDefaultFrom,
    );

    const [to, setTo] = useState(
        createDefaultTo,
    );

    const [status, setStatus] =
        useState<HistoryStatus>("IDLE");

    const [loadedCount, setLoadedCount] =
        useState(0);

    const [errorMessage, setErrorMessage] =
        useState<string | null>(null);

    function setRecentRange(minutes: number) {
        const now = new Date();

        setFrom(
            toDateTimeLocal(
                new Date(
                    now.getTime() -
                    minutes * 60_000,
                ),
            ),
        );

        setTo(toDateTimeLocal(now));
        setStatus("IDLE");
        setErrorMessage(null);
    }

    function setTodayRange() {
        const now = new Date();

        const start = new Date(
            now.getFullYear(),
            now.getMonth(),
            now.getDate(),
            0,
            0,
            0,
        );

        setFrom(toDateTimeLocal(start));
        setTo(toDateTimeLocal(now));
        setStatus("IDLE");
        setErrorMessage(null);
    }

    async function handleSearch() {
        if (!from || !to) {
            setStatus("ERROR");
            setErrorMessage(
                "시작 시각과 종료 시각을 입력해 주세요.",
            );
            return;
        }

        if (
            new Date(from).getTime() >
            new Date(to).getTime()
        ) {
            setStatus("ERROR");
            setErrorMessage(
                "시작 시각은 종료 시각보다 늦을 수 없습니다.",
            );
            return;
        }

        setStatus("LOADING");
        setErrorMessage(null);

        const query = new URLSearchParams({
            from: normalizeDateTime(from),
            to: normalizeDateTime(to),
            limit: "200",
        });

        try {
            const response = await fetch(
                `/api/drones/${droneId}` +
                `/telemetry/history?${query}`,
                {
                    method: "GET",
                    headers: {
                        Accept: "application/json",
                    },
                    cache: "no-store",
                },
            );

            if (!response.ok) {
                throw new Error(
                    `경로 조회 실패: ${response.status}`,
                );
            }

            const payload: unknown =
                await response.json();

            if (!Array.isArray(payload)) {
                throw new Error(
                    "경로 조회 응답이 배열이 아닙니다.",
                );
            }

            const points = (
                payload as DroneTelemetryHistory[]
            )
                .map(toTrackPoint)
                .filter(
                    (
                        point,
                    ): point is DroneTrackPoint =>
                        point !== null,
                );

            onHistoryLoaded(points);
            setLoadedCount(points.length);

            setStatus(
                points.length > 0
                    ? "SUCCESS"
                    : "EMPTY",
            );
        } catch (error) {
            console.error(
                "과거 경로 조회 오류:",
                error,
            );

            setStatus("ERROR");
            setErrorMessage(
                error instanceof Error
                    ? error.message
                    : "알 수 없는 오류가 발생했습니다.",
            );
        }
    }

    const displayCount =
        status === "SUCCESS" ||
        status === "EMPTY"
            ? loadedCount
            : currentPointCount;

    return (
        <section className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h3 className="font-semibold text-slate-900">
                        과거 비행 경로 조회
                    </h3>

                    <p className="mt-1 text-xs text-slate-500">
                        선택한 시간 범위의 저장된 좌표를
                        지도에 표시합니다.
                    </p>
                </div>

                <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-600">
                    {statusText(
                        status,
                        displayCount,
                    )}
                </span>
            </div>

            <div className="mb-3 flex flex-wrap gap-2">
                <button
                    type="button"
                    onClick={() =>
                        setRecentRange(10)
                    }
                    className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700"
                >
                    최근 10분
                </button>

                <button
                    type="button"
                    onClick={() =>
                        setRecentRange(60)
                    }
                    className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700"
                >
                    최근 1시간
                </button>

                <button
                    type="button"
                    onClick={setTodayRange}
                    className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700"
                >
                    오늘
                </button>
            </div>

            <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
                <label className="space-y-1">
                    <span className="text-xs font-medium text-slate-600">
                        시작 시각
                    </span>

                    <input
                        type="datetime-local"
                        value={from}
                        onChange={(event) =>
                            setFrom(
                                event.target.value,
                            )
                        }
                        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                    />
                </label>

                <label className="space-y-1">
                    <span className="text-xs font-medium text-slate-600">
                        종료 시각
                    </span>

                    <input
                        type="datetime-local"
                        value={to}
                        onChange={(event) =>
                            setTo(
                                event.target.value,
                            )
                        }
                        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                    />
                </label>

                <button
                    type="button"
                    onClick={() =>
                        void handleSearch()
                    }
                    disabled={status === "LOADING"}
                    className="self-end rounded-lg bg-blue-600 px-5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                    {status === "LOADING"
                        ? "조회 중"
                        : "경로 조회"}
                </button>
            </div>

            {errorMessage && (
                <p className="mt-3 text-sm text-red-600">
                    {errorMessage}
                </p>
            )}
        </section>
    );
}