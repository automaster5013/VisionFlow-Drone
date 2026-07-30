import type { DroneStatus } from "@/types/drone";

interface DroneStatusBadgeProps {
    status: DroneStatus;
}

const statusLabels: Record<DroneStatus, string> = {
    OFFLINE: "오프라인",
    ONLINE: "온라인",
    FLYING: "비행 중",
    CHARGING: "충전 중",
    MAINTENANCE: "점검 중",
    ERROR: "오류",
};

const statusStyles: Record<DroneStatus, string> = {
    OFFLINE: "border-slate-200 bg-slate-100 text-slate-700",
    ONLINE: "border-emerald-200 bg-emerald-50 text-emerald-700",
    FLYING: "border-sky-200 bg-sky-50 text-sky-700",
    CHARGING: "border-amber-200 bg-amber-50 text-amber-700",
    MAINTENANCE: "border-violet-200 bg-violet-50 text-violet-700",
    ERROR: "border-red-200 bg-red-50 text-red-700",
};

const dotStyles: Record<DroneStatus, string> = {
    OFFLINE: "bg-slate-400",
    ONLINE: "bg-emerald-500",
    FLYING: "bg-sky-500",
    CHARGING: "bg-amber-500",
    MAINTENANCE: "bg-violet-500",
    ERROR: "bg-red-500",
};

export function DroneStatusBadge({
                                     status,
                                 }: DroneStatusBadgeProps) {
    return (
        <span
            className={[
                "inline-flex items-center gap-2 rounded-full border",
                "px-3 py-1 text-xs font-semibold",
                statusStyles[status],
            ].join(" ")}
        >
      <span
          aria-hidden="true"
          className={`h-2 w-2 rounded-full ${dotStyles[status]}`}
      />

            {statusLabels[status]}
    </span>
    );
}