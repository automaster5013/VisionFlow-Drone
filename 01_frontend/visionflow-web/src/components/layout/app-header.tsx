import { CommandClock } from "@/components/layout/command-clock";
import { MobileNavigation } from "@/components/layout/mobile-navigation";
import { OperatorSessionControls } from "@/components/security/operator-session-controls";
import { ThemeSelector } from "@/components/theme/theme-selector";
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
      className: "vf-status-badge--danger",
    };
  }
  if (!status.enabled) {
    return {
      label: "LOCAL · RBAC OFF",
      className: "vf-status-badge--info",
    };
  }
  if (status.role === "INVALID_KEY") {
    return {
      label: "RBAC KEY INVALID",
      className: "vf-status-badge--danger",
    };
  }
  if (status.role === "INVALID_SESSION") {
    return {
      label: "SESSION EXPIRED",
      className: "vf-status-badge--danger",
    };
  }
  if (!status.authenticated) {
    return {
      label:
        authMode === "session"
          ? "LOGIN REQUIRED"
          : "RBAC KEY REQUIRED",
      className: "vf-status-badge--warning",
    };
  }
  return {
    label: `${status.username ?? "operator"} · ${status.role ?? "UNKNOWN"}`,
    className: "vf-status-badge--healthy",
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
    <header className="vf-command-header">
      <div className="vf-command-header__inner">
        <div className="flex min-w-0 items-center gap-3">
          <MobileNavigation operatorSecurity={operatorSecurity} />

          <div className="vf-command-header__brand">
            <p className="vf-command-header__eyebrow">
              VisionFlow Command Center
            </p>
            <p className="vf-command-header__title">
              Drone · Vision AI · Safety Operations
            </p>
          </div>
        </div>

        <div className="vf-command-header__status" aria-label="관제 시각">
          <div>
            <p className="vf-command-eyebrow">Control surface</p>
            <p className="mt-1 text-xs font-bold text-[var(--vf-text-secondary)]">
              Phase 3 · Edge Operations
            </p>
          </div>
          <CommandClock />
        </div>

        <div className="vf-command-header__actions">
          <span
            className={`vf-status-badge ${badge.className}`}
            title="현재 운영 권한 상태"
          >
            {badge.label}
          </span>

          <ThemeSelector />

          <OperatorSessionControls
            authMode={operatorAuthMode}
            status={operatorSecurity}
          />
        </div>
      </div>
    </header>
  );
}
