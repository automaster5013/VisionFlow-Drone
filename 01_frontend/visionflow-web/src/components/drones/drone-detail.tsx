import Link from "next/link";

import { DroneAutoRefresh } from "@/components/drones/drone-auto-refresh";
import { DroneLocationMap } from "@/components/drones/map/drone-location-map";
import { DroneStatusBadge } from "@/components/drones/drone-status-badge";
import { TelemetryUpdateForm } from "@/components/drones/telemetry-update-form";
import { formatKoreanDateTime } from "@/lib/date";
import type { Drone } from "@/types/drone";

interface DroneDetailProps {
    drone: Drone;
}

function formatNumber(
    value: number | null,
    digits = 2,
): string {
    if (value === null) {
        return "-";
    }

    return value.toFixed(digits);
}

function formatBattery(
    value: number | null,
): string {
    return value === null ? "-" : `${value}%`;
}

export function DroneDetail({
                                drone,
                            }: DroneDetailProps) {
    return (
        <section>
            <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
                <div>
                    <Link
                        href="/drones"
                        className="text-sm font-semibold text-sky-700 hover:text-sky-900"
                    >
                        ← 드론 목록
                    </Link>

                    <p className="mt-5 text-sm font-semibold uppercase tracking-wider text-sky-700">
                        Drone Details
                    </p>

                    <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-950">
                        {drone.name}
                    </h1>

                    <p className="mt-2 font-mono text-sm text-slate-500">
                        {drone.droneCode}
                    </p>
                </div>

                <div className="flex flex-col items-start gap-3 lg:items-end">
                    <DroneStatusBadge status={drone.status} />

                    <DroneAutoRefresh intervalMs={5000} />
                </div>
            </div>

            <div className="mt-7 grid gap-5 xl:grid-cols-3">
                <div className="space-y-5 xl:col-span-2">
                    <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                        <h2 className="text-lg font-bold text-slate-950">
                            실시간 운항 정보
                        </h2>

                        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                            <MetricCard
                                label="배터리"
                                value={formatBattery(
                                    drone.batteryLevel,
                                )}
                            />

                            <MetricCard
                                label="고도"
                                value={
                                    drone.altitude === null
                                        ? "-"
                                        : `${formatNumber(
                                            drone.altitude,
                                        )} m`
                                }
                            />

                            <MetricCard
                                label="위도"
                                value={formatNumber(
                                    drone.latitude,
                                    7,
                                )}
                            />

                            <MetricCard
                                label="경도"
                                value={formatNumber(
                                    drone.longitude,
                                    7,
                                )}
                            />
                        </div>
                    </article>

                    <article className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                        <div className="flex flex-col justify-between gap-3 border-b border-slate-200 p-6 sm:flex-row sm:items-center">
                            <div>
                                <h2 className="text-lg font-bold text-slate-950">
                                    현재 위치
                                </h2>

                                <p className="mt-1 text-sm text-slate-500">
                                    최근 수신한 GPS 좌표를 지도에
                                    표시합니다.
                                </p>
                            </div>

                            {drone.latitude !== null &&
                                drone.longitude !== null && (
                                    <div className="font-mono text-xs text-slate-500">
                                        {drone.latitude.toFixed(7)},{" "}
                                        {drone.longitude.toFixed(7)}
                                    </div>
                                )}
                        </div>

                        <DroneLocationMap drone={drone} />
                    </article>

                    <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                        <h2 className="text-lg font-bold text-slate-950">
                            연결 및 영상 정보
                        </h2>

                        <dl className="mt-6 grid gap-6 sm:grid-cols-2">
                            <DetailItem
                                label="최근 연결 시각"
                                value={
                                    drone.lastConnectedAt
                                        ? formatKoreanDateTime(
                                            drone.lastConnectedAt,
                                        )
                                        : "-"
                                }
                            />

                            <DetailItem
                                label="최근 수정 시각"
                                value={formatKoreanDateTime(
                                    drone.updatedAt,
                                )}
                            />

                            <div className="sm:col-span-2">
                                <DetailItem
                                    label="RTSP URL"
                                    value={drone.rtspUrl ?? "-"}
                                    monospace
                                />
                            </div>
                        </dl>
                    </article>

                    <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                        <h2 className="text-lg font-bold text-slate-950">
                            기체 기본 정보
                        </h2>

                        <dl className="mt-6 grid gap-6 sm:grid-cols-2">
                            <DetailItem
                                label="모델명"
                                value={drone.modelName ?? "-"}
                            />

                            <DetailItem
                                label="시리얼 번호"
                                value={drone.serialNumber ?? "-"}
                                monospace
                            />

                            <DetailItem
                                label="등록 시각"
                                value={formatKoreanDateTime(
                                    drone.createdAt,
                                )}
                            />

                            <DetailItem
                                label="드론 ID"
                                value={String(drone.id)}
                            />
                        </dl>
                    </article>
                </div>

                <div>
                    <TelemetryUpdateForm drone={drone} />
                </div>
            </div>
        </section>
    );
}

interface MetricCardProps {
    label: string;
    value: string;
}

function MetricCard({
                        label,
                        value,
                    }: MetricCardProps) {
    return (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm font-medium text-slate-500">
                {label}
            </p>

            <p className="mt-2 break-all text-xl font-bold text-slate-950">
                {value}
            </p>
        </div>
    );
}

interface DetailItemProps {
    label: string;
    value: string;
    monospace?: boolean;
}

function DetailItem({
                        label,
                        value,
                        monospace = false,
                    }: DetailItemProps) {
    return (
        <div>
            <dt className="text-sm font-medium text-slate-500">
                {label}
            </dt>

            <dd
                className={[
                    "mt-2 break-all text-sm text-slate-900",
                    monospace ? "font-mono" : "",
                ].join(" ")}
            >
                {value}
            </dd>
        </div>
    );
}