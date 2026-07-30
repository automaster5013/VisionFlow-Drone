"use client";

import { useState } from "react";

import { useOperatorAccess } from "@/components/security/operator-access-provider";
import type {
    ApiErrorResponse,
    ApiResponse,
    DeleteResponse,
    Drone,
    DroneStatus,
} from "@/types/drone";

interface DroneActionsProps {
    drone: Drone;
    onEdit: (drone: Drone) => void;
    onChanged: () => void;
}

const statuses: Array<{
    value: DroneStatus;
    label: string;
}> = [
    { value: "OFFLINE", label: "오프라인" },
    { value: "ONLINE", label: "온라인" },
    { value: "FLYING", label: "비행 중" },
    { value: "CHARGING", label: "충전 중" },
    { value: "MAINTENANCE", label: "점검 중" },
    { value: "ERROR", label: "오류" },
];

export function DroneActions({
                                 drone,
                                 onEdit,
                                 onChanged,
                             }: DroneActionsProps) {
    const [processing, setProcessing] = useState(false);
    const [message, setMessage] = useState<string | null>(null);
    const {
        canOperate,
        canAdminister,
        operateDeniedReason,
        adminDeniedReason,
    } = useOperatorAccess();

    async function updateStatus(
        status: DroneStatus,
    ): Promise<void> {
        if (status === drone.status) {
            return;
        }

        if (!canOperate) {
            setMessage(operateDeniedReason);
            return;
        }

        setProcessing(true);
        setMessage(null);

        try {
            const response = await fetch(
                `/api/drones/${drone.id}/status`,
                {
                    method: "PATCH",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({ status }),
                },
            );

            const body = (await response.json()) as
                | ApiResponse<Drone>
                | ApiErrorResponse;

            if (!response.ok || !body.success) {
                const errorBody = body as ApiErrorResponse;

                setMessage(
                    errorBody.message || "상태 변경에 실패했습니다.",
                );
                return;
            }

            onChanged();
        } catch (error) {
            setMessage(
                error instanceof Error
                    ? error.message
                    : "상태 변경 중 오류가 발생했습니다.",
            );
        } finally {
            setProcessing(false);
        }
    }

    async function deleteDrone(): Promise<void> {
        if (!canAdminister) {
            setMessage(adminDeniedReason);
            return;
        }

        const confirmed = window.confirm(
            `${drone.name} 드론을 삭제하시겠습니까?\n삭제된 데이터는 복구할 수 없습니다.`,
        );

        if (!confirmed) {
            return;
        }

        setProcessing(true);
        setMessage(null);

        try {
            const response = await fetch(
                `/api/drones/${drone.id}`,
                {
                    method: "DELETE",
                },
            );

            const body = (await response.json()) as
                | ApiResponse<DeleteResponse>
                | ApiErrorResponse;

            if (!response.ok || !body.success) {
                const errorBody = body as ApiErrorResponse;

                setMessage(
                    errorBody.message || "드론 삭제에 실패했습니다.",
                );
                return;
            }

            onChanged();
        } catch (error) {
            setMessage(
                error instanceof Error
                    ? error.message
                    : "드론 삭제 중 오류가 발생했습니다.",
            );
        } finally {
            setProcessing(false);
        }
    }

    return (
        <div className="min-w-48">
            <div className="flex items-center justify-end gap-2">
                <select
                    aria-label={`${drone.name} 상태 변경`}
                    value={drone.status}
                    disabled={processing || !canOperate}
                    title={canOperate ? undefined : operateDeniedReason ?? undefined}
                    onChange={(event) =>
                        updateStatus(event.target.value as DroneStatus)
                    }
                    className="rounded-lg border border-slate-300 bg-white px-2 py-2 text-xs text-slate-700"
                >
                    {statuses.map((status) => (
                        <option
                            key={status.value}
                            value={status.value}
                        >
                            {status.label}
                        </option>
                    ))}
                </select>

                <button
                    type="button"
                    disabled={processing || !canOperate}
                    title={canOperate ? undefined : operateDeniedReason ?? undefined}
                    onClick={() => onEdit(drone)}
                    className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                    수정
                </button>

                <button
                    type="button"
                    disabled={processing || !canAdminister}
                    title={canAdminister ? undefined : adminDeniedReason ?? undefined}
                    onClick={deleteDrone}
                    className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-100 disabled:opacity-50"
                >
                    삭제
                </button>
            </div>

            {message && (
                <p className="mt-2 text-right text-xs text-red-600">
                    {message}
                </p>
            )}
        </div>
    );
}
