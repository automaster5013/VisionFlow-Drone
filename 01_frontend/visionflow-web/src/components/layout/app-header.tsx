import { MobileNavigation } from "@/components/layout/mobile-navigation";
import { OperatorSessionControls } from "@/components/security/operator-session-controls";
import type {
    OperatorAuthMode,
    OperatorSecurityStatus,
} from "@/types/operator-security";

function resolveOperatorBadge(
    status: OperatorSecurityStatus | null,
    authMode: OperatorAuthMode,
) {
    if (!status) {
        return {
            label: "BACKEND OFFLINE",
            className: "border-rose-200 bg-rose-50 text-rose-700",
        };
    }
    if (!status.enabled) {
        return {
            label: "LOCAL · RBAC OFF",
            className: "border-sky-200 bg-sky-50 text-sky-700",
        };
    }
    if (status.role === "INVALID_KEY") {
        return {
            label: "RBAC KEY INVALID",
            className: "border-rose-200 bg-rose-50 text-rose-700",
        };
    }
    if (status.role === "INVALID_SESSION") {
        return {
            label: "SESSION EXPIRED",
            className: "border-rose-200 bg-rose-50 text-rose-700",
        };
    }
    if (!status.authenticated) {
        return {
            label:
                authMode === "session"
                    ? "LOGIN REQUIRED"
                    : "RBAC KEY REQUIRED",
            className: "border-amber-200 bg-amber-50 text-amber-700",
        };
    }
    return {
        label: `${status.username ?? "operator"} · ${status.role ?? "UNKNOWN"}`,
        className: "border-emerald-200 bg-emerald-50 text-emerald-700",
    };
}

interface AppHeaderProps {
    operatorSecurity: OperatorSecurityStatus | null;
    operatorAuthMode: OperatorAuthMode;
}

export function AppHeader({
    operatorSecurity,
    operatorAuthMode,
}: AppHeaderProps) {
    const badge = resolveOperatorBadge(operatorSecurity, operatorAuthMode);

    return (
        <header className="sticky top-0 z-30 border-b border-slate-200/90 bg-white/95 backdrop-blur">
            <div className="flex min-h-[72px] items-center justify-between gap-3 px-4 sm:px-8">
                <div className="flex min-w-0 items-center gap-3">
                    <MobileNavigation operatorSecurity={operatorSecurity} />

                    <div className="min-w-0">
                        <p className="truncate text-sm font-bold text-slate-900">
                            VisionFlow Mission Control
                        </p>

                        <p className="hidden truncate text-xs text-slate-500 sm:block">
                            Drone · Vision AI · Operations
                        </p>
                    </div>
                </div>

                <div className="flex shrink-0 items-center gap-2 sm:gap-3">
                    <span className="hidden text-sm text-slate-500 sm:inline">
                        운영 권한
                    </span>

                    <span
                        className={`hidden max-w-56 truncate rounded-full border px-3 py-1.5 text-xs font-bold sm:inline ${badge.className}`}
                    >
                        {badge.label}
                    </span>
                    <OperatorSessionControls
                        authMode={operatorAuthMode}
                        status={operatorSecurity}
                    />
                </div>
            </div>
        </header>
    );
}
