"use client";

import {
    useMemo,
    useState,
} from "react";
import { useRouter } from "next/navigation";
import { DroneAutoRefresh } from "@/components/drones/drone-auto-refresh";
import { DroneFormModal } from "@/components/drones/drone-form-modal";
import { DroneList } from "@/components/drones/drone-list";
import { useOperatorAccess } from "@/components/security/operator-access-provider";
import {
    DroneStatusFilter,
    type DroneStatusFilterValue,
} from "@/components/drones/drone-status-filter";
import type { Drone } from "@/types/drone";

interface DronePageClientProps {
    initialDrones: Drone[];
}

export function DronePageClient({
                                    initialDrones,
                                }: DronePageClientProps) {
    const router = useRouter();
    const { canOperate, operateDeniedReason } = useOperatorAccess();

    const [filter, setFilter] =
        useState<DroneStatusFilterValue>("ALL");

    const [formOpen, setFormOpen] = useState(false);

    const [editingDrone, setEditingDrone] =
        useState<Drone | null>(null);

    const filteredDrones = useMemo(() => {
        if (filter === "ALL") {
            return initialDrones;
        }

        return initialDrones.filter(
            (drone) => drone.status === filter,
        );
    }, [initialDrones, filter]);

    const statusCounts = useMemo(() => {
        return initialDrones.reduce(
            (counts, drone) => {
                counts.total += 1;

                if (
                    drone.status === "ONLINE" ||
                    drone.status === "FLYING"
                ) {
                    counts.connected += 1;
                }

                if (drone.status === "ERROR") {
                    counts.error += 1;
                }

                if (drone.status === "MAINTENANCE") {
                    counts.maintenance += 1;
                }

                return counts;
            },
            {
                total: 0,
                connected: 0,
                maintenance: 0,
                error: 0,
            },
        );
    }, [initialDrones]);

    function openCreateForm(): void {
        if (!canOperate) {
            return;
        }

        setEditingDrone(null);
        setFormOpen(true);
    }

    function openEditForm(drone: Drone): void {
        if (!canOperate) {
            return;
        }

        setEditingDrone(drone);
        setFormOpen(true);
    }

    function closeForm(): void {
        setFormOpen(false);
        setEditingDrone(null);
    }

    function refreshPage(): void {
        router.refresh();
    }

    return (
        <>
            <section>
                <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
                    <div>
                        <p className="text-sm font-semibold uppercase tracking-wider text-sky-700">
                            Device Management
                        </p>

                        <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-950">
                            드론 관리
                        </h1>

                        <p className="mt-2 text-sm leading-6 text-slate-600">
                            관제 플랫폼에 연결되는 드론과 RTSP 스트림
                            정보를 관리합니다.
                        </p>
                    </div>

                    <div className="flex flex-col items-start gap-3 lg:items-end">
                        <button
                            type="button"
                            onClick={openCreateForm}
                            disabled={!canOperate}
                            title={canOperate ? undefined : operateDeniedReason ?? undefined}
                            className="rounded-lg bg-slate-900 px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            드론 등록
                        </button>

                        <DroneAutoRefresh intervalMs={5000} />
                    </div>
                </div>

                <div className="mt-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                    <SummaryCard
                        label="전체 드론"
                        value={statusCounts.total}
                    />

                    <SummaryCard
                        label="연결·비행 중"
                        value={statusCounts.connected}
                    />

                    <SummaryCard
                        label="점검 중"
                        value={statusCounts.maintenance}
                    />

                    <SummaryCard
                        label="오류"
                        value={statusCounts.error}
                    />
                </div>

                <div className="mt-7 flex flex-col justify-between gap-4 lg:flex-row lg:items-center">
                    <DroneStatusFilter
                        value={filter}
                        onChange={setFilter}
                    />

                    <p className="text-sm text-slate-500">
                        총 {filteredDrones.length}대 표시
                    </p>
                </div>

                <div className="mt-5">
                    <DroneList
                        drones={filteredDrones}
                        onEdit={openEditForm}
                        onChanged={refreshPage}
                    />
                </div>
            </section>

            {formOpen && (
                <DroneFormModal
                    key={
                        editingDrone
                            ? `edit-${editingDrone.id}`
                            : "create"
                    }
                    mode={editingDrone ? "edit" : "create"}
                    drone={editingDrone}
                    onClose={closeForm}
                    onSuccess={refreshPage}
                />
            )}
        </>
    );
}

interface SummaryCardProps {
    label: string;
    value: number;
}

function SummaryCard({
                         label,
                         value,
                     }: SummaryCardProps) {
    return (
        <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-sm font-medium text-slate-500">
                {label}
            </p>

            <p className="mt-2 text-3xl font-bold text-slate-950">
                {value}
            </p>
        </article>
    );
}
