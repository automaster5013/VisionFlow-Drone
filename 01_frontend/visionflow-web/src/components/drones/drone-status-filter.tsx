"use client";

import type { DroneStatus } from "@/types/drone";

export type DroneStatusFilterValue = "ALL" | DroneStatus;

interface DroneStatusFilterProps {
    value: DroneStatusFilterValue;
    onChange: (value: DroneStatusFilterValue) => void;
}

const filterItems: Array<{
    value: DroneStatusFilterValue;
    label: string;
}> = [
    { value: "ALL", label: "전체" },
    { value: "ONLINE", label: "온라인" },
    { value: "FLYING", label: "비행 중" },
    { value: "CHARGING", label: "충전 중" },
    { value: "MAINTENANCE", label: "점검 중" },
    { value: "OFFLINE", label: "오프라인" },
    { value: "ERROR", label: "오류" },
];

export function DroneStatusFilter({
                                      value,
                                      onChange,
                                  }: DroneStatusFilterProps) {
    return (
        <div
            className="flex flex-wrap gap-2"
            aria-label="드론 상태 필터"
        >
            {filterItems.map((item) => {
                const active = item.value === value;

                return (
                    <button
                        key={item.value}
                        type="button"
                        onClick={() => onChange(item.value)}
                        className={[
                            "rounded-full border px-4 py-2 text-sm font-medium",
                            "transition-colors",
                            active
                                ? "border-slate-900 bg-slate-900 text-white"
                                : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50",
                        ].join(" ")}
                    >
                        {item.label}
                    </button>
                );
            })}
        </div>
    );
}