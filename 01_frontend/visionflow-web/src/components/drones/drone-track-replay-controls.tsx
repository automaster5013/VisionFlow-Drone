"use client";

import type {
    DroneTrackPoint,
} from "@/hooks/use-drone-fleet-telemetry";

export interface DroneReplayState {
    droneId: number;
    cursor: number;
    pointCount: number;
    isPlaying: boolean;
    intervalMs: number;
}

interface DroneTrackReplayControlsProps {
    droneId: number;
    points: DroneTrackPoint[];
    replayState: DroneReplayState | null;
    onChange: (
        state: DroneReplayState,
    ) => void;
    onExit: () => void;
}

function formatTime(timestamp: number): string {
    return new Date(timestamp).toLocaleString(
        "ko-KR",
    );
}

export function DroneTrackReplayControls({
                                             droneId,
                                             points,
                                             replayState,
                                             onChange,
                                             onExit,
                                         }: DroneTrackReplayControlsProps) {
    const activeState =
        replayState?.droneId === droneId
            ? replayState
            : null;

    if (points.length < 2) {
        return (
            <section className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <h3 className="font-semibold text-slate-900">
                    과거 경로 재생
                </h3>

                <p className="mt-2 text-sm text-slate-500">
                    재생하려면 서로 다른 경로 지점이
                    2개 이상 필요합니다.
                </p>
            </section>
        );
    }

    if (!activeState) {
        return (
            <section className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
                <div>
                    <h3 className="font-semibold text-slate-900">
                        과거 경로 재생
                    </h3>

                    <p className="mt-1 text-sm text-slate-500">
                        총 {points.length}개 지점을
                        시간순으로 재생합니다.
                    </p>
                </div>

                <button
                    type="button"
                    onClick={() =>
                        onChange({
                            droneId,
                            cursor: 0,
                            pointCount:
                            points.length,
                            isPlaying: true,
                            intervalMs: 1_000,
                        })
                    }
                    className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-white"
                >
                    경로 재생 시작
                </button>
            </section>
        );
    }

    const currentReplayState = activeState;

    const pointCount = Math.min(
        currentReplayState.pointCount,
        points.length,
    );

    const maxIndex = Math.max(
        pointCount - 1,
        0,
    );

    const safeCursor = Math.min(
        currentReplayState.cursor,
        maxIndex,
    );

    const currentPoint = points[safeCursor];

    function togglePlayback() {
        const restartFromBeginning =
            !currentReplayState.isPlaying &&
            safeCursor >= maxIndex;

        onChange({
            ...currentReplayState,
            cursor: restartFromBeginning
                ? 0
                : safeCursor,
            isPlaying:
                !currentReplayState.isPlaying,
        });
    }

    return (
        <section className="space-y-4 rounded-xl border border-amber-300 bg-amber-50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-slate-900">
                            과거 경로 재생
                        </h3>

                        <span className="rounded-full bg-amber-200 px-2 py-1 text-xs font-semibold text-amber-800">
                            REPLAY
                        </span>
                    </div>

                    <p className="mt-1 text-sm text-slate-600">
                        {safeCursor + 1} /{" "}
                        {pointCount} 지점
                    </p>
                </div>

                <div className="flex flex-wrap gap-2">
                    <button
                        type="button"
                        onClick={togglePlayback}
                        className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
                    >
                        {currentReplayState.isPlaying
                            ? "일시정지"
                            : "재생"}
                    </button>

                    <button
                        type="button"
                        onClick={onExit}
                        className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700"
                    >
                        라이브로 복귀
                    </button>
                </div>
            </div>

            <input
                type="range"
                min={0}
                max={maxIndex}
                value={safeCursor}
                onChange={(event) =>
                    onChange({
                        ...currentReplayState,
                        cursor: Number(
                            event.target.value,
                        ),
                        isPlaying: false,
                    })
                }
                className="w-full accent-amber-500"
            />

            <div className="grid gap-3 text-sm sm:grid-cols-3">
                <div className="rounded-lg bg-white p-3">
                    <div className="text-xs text-slate-500">
                        기록 시각
                    </div>

                    <div className="mt-1 font-medium text-slate-900">
                        {currentPoint
                            ? formatTime(
                                currentPoint.receivedAt,
                            )
                            : "-"}
                    </div>
                </div>

                <div className="rounded-lg bg-white p-3">
                    <div className="text-xs text-slate-500">
                        기록 고도
                    </div>

                    <div className="mt-1 font-medium text-slate-900">
                        {currentPoint?.altitude ??
                            0}
                        m
                    </div>
                </div>

                <label className="rounded-lg bg-white p-3">
                    <span className="text-xs text-slate-500">
                        재생 속도
                    </span>

                    <select
                        value={currentReplayState.intervalMs}
                        onChange={(event) =>
                            onChange({
                                ...currentReplayState,
                                intervalMs: Number(
                                    event.target.value,
                                ),
                            })
                        }
                        className="mt-1 block w-full bg-transparent font-medium text-slate-900 outline-none"
                    >
                        <option value={1_000}>
                            1배속
                        </option>
                        <option value={500}>
                            2배속
                        </option>
                        <option value={250}>
                            4배속
                        </option>
                    </select>
                </label>
            </div>
        </section>
    );
}