"use client";

import { DroneActions } from "@/components/drones/drone-actions";
import { DroneStatusBadge } from "@/components/drones/drone-status-badge";
import { formatKoreanDateTime } from "@/lib/date";
import type { Drone } from "@/types/drone";
import Link from "next/link";

interface DroneListProps {
    drones: Drone[];
    onEdit: (drone: Drone) => void;
    onChanged: () => void;
}

function formatBattery(
    batteryLevel: number | null,
): string {
    return batteryLevel === null
        ? "-"
        : `${batteryLevel}%`;
}

function formatCoordinate(
    value: number | null,
): string {
    return value === null ? "-" : value.toFixed(6);
}

export function DroneList({
                              drones,
                              onEdit,
                              onChanged,
                          }: DroneListProps) {
    if (drones.length === 0) {
        return (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
                <h2 className="text-lg font-bold text-slate-900">
                    등록된 드론이 없습니다.
                </h2>

                <p className="mt-2 text-sm text-slate-500">
                    드론 등록 버튼을 눌러 첫 번째 기체를 등록하세요.
                </p>
            </div>
        );
    }

    return (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200">
                    <thead className="bg-slate-50">
                    <tr>
                        <TableHeader>드론</TableHeader>
                        <TableHeader>모델·시리얼</TableHeader>
                        <TableHeader>상태</TableHeader>
                        <TableHeader>배터리</TableHeader>
                        <TableHeader>위치</TableHeader>
                        <TableHeader>최근 연결</TableHeader>

                        <th
                            scope="col"
                            className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-wider text-slate-500"
                        >
                            관리
                        </th>
                    </tr>
                    </thead>

                    <tbody className="divide-y divide-slate-100">
                    {drones.map((drone) => (
                        <tr
                            key={drone.id}
                            className="hover:bg-slate-50/70"
                        >
                            <td className="whitespace-nowrap px-5 py-4">
                                <Link
                                    href={`/drones/${drone.id}`}
                                    className="mt-1 block font-mono text-xs text-slate-500 hover:text-sky-700"
                                >
                                    {drone.droneCode}
                                </Link>

                                <p className="mt-1 font-mono text-xs text-slate-500">
                                    {drone.droneCode}
                                </p>
                            </td>

                            <td className="px-5 py-4">
                                <p className="text-sm text-slate-800">
                                    {drone.modelName ?? "-"}
                                </p>

                                <p className="mt-1 font-mono text-xs text-slate-500">
                                    {drone.serialNumber ?? "-"}
                                </p>
                            </td>

                            <td className="whitespace-nowrap px-5 py-4">
                                <DroneStatusBadge status={drone.status} />
                            </td>

                            <td className="whitespace-nowrap px-5 py-4 text-sm font-semibold text-slate-800">
                                {formatBattery(drone.batteryLevel)}
                            </td>

                            <td className="whitespace-nowrap px-5 py-4 font-mono text-xs text-slate-600">
                                <p>{formatCoordinate(drone.latitude)}</p>
                                <p className="mt-1">
                                    {formatCoordinate(drone.longitude)}
                                </p>
                            </td>

                            <td className="whitespace-nowrap px-5 py-4 text-xs text-slate-600">
                                {drone.lastConnectedAt
                                    ? formatKoreanDateTime(
                                        drone.lastConnectedAt,
                                    )
                                    : "-"}
                            </td>

                            <td className="px-5 py-4">
                                <DroneActions
                                    drone={drone}
                                    onEdit={onEdit}
                                    onChanged={onChanged}
                                />
                            </td>
                        </tr>
                    ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

interface TableHeaderProps {
    children: React.ReactNode;
}

function TableHeader({
                         children,
                     }: TableHeaderProps) {
    return (
        <th
            scope="col"
            className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500"
        >
            {children}
        </th>
    );
}