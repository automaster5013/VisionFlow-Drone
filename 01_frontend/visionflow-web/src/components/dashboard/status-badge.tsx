import type { ServiceStatus } from "@/types/health";

interface StatusBadgeProps {
    status: ServiceStatus;
}

const statusStyles: Record<ServiceStatus, string> = {
    UP: "border-emerald-200 bg-emerald-50 text-emerald-700",
    DOWN: "border-red-200 bg-red-50 text-red-700",
    UNKNOWN: "border-slate-200 bg-slate-100 text-slate-600",
};

const dotStyles: Record<ServiceStatus, string> = {
    UP: "bg-emerald-500",
    DOWN: "bg-red-500",
    UNKNOWN: "bg-slate-400",
};

export function StatusBadge({ status }: StatusBadgeProps) {
    const normalizedStatus: ServiceStatus =
        status === "UP" || status === "DOWN" ? status : "UNKNOWN";

    return (
        <span
            className={[
                "inline-flex items-center gap-2 rounded-full border px-3 py-1",
                "text-xs font-semibold tracking-wide",
                statusStyles[normalizedStatus],
            ].join(" ")}
        >
      <span
          aria-hidden="true"
          className={`h-2 w-2 rounded-full ${dotStyles[normalizedStatus]}`}
      />

            {normalizedStatus}
    </span>
    );
}