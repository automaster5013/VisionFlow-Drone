import type { Metadata } from "next";
import Link from "next/link";

import { CspReportMonitor } from "@/components/security/csp-report-monitor";
import { OperatorAccessDenied } from "@/components/security/operator-access-denied";
import { SecurityHeaderProbe } from "@/components/security/security-header-probe";
import { getOperatorAuthMode } from "@/lib/server/operator-auth";
import { getOperatorSecurityStatus } from "@/lib/server/operator-security";
import { getOperatorSessions } from "@/lib/server/operator-session-management";
import { requireOperatorPageAccess } from "@/lib/server/protected-page";
import type { OperatorManagedSession } from "@/types/operator-session-management";

export const metadata: Metadata = {
  title: "운영 보안 상태",
};

export const dynamic = "force-dynamic";

interface StatusCardProps {
  label: string;
  value: string;
  detail: string;
  tone?: "good" | "warning" | "neutral";
}

function StatusCard({
  label,
  value,
  detail,
  tone = "neutral",
}: StatusCardProps) {
  const toneClass = {
    good: "border-emerald-200 bg-emerald-50/70",
    warning: "border-amber-200 bg-amber-50/70",
    neutral: "border-slate-200 bg-white",
  }[tone];
  return (
    <article className={`rounded-2xl border p-5 shadow-sm ${toneClass}`}>
      <p className="text-xs font-bold uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="mt-2 text-2xl font-black text-slate-950">{value}</p>
      <p className="mt-2 text-sm leading-6 text-slate-600">{detail}</p>
    </article>
  );
}

function durationLabel(start: string, end: string): string {
  const milliseconds = new Date(end).getTime() - new Date(start).getTime();
  if (!Number.isFinite(milliseconds) || milliseconds <= 0) {
    return "확인 불가";
  }
  const minutes = Math.round(milliseconds / 60_000);
  if (minutes >= 60 && minutes % 60 === 0) {
    return `${minutes / 60}시간`;
  }
  return `${minutes}분`;
}

async function loadSessions(canAdminister: boolean): Promise<{
  sessions: OperatorManagedSession[] | null;
  error: string | null;
}> {
  if (!canAdminister) {
    return { sessions: null, error: null };
  }
  try {
    return { sessions: await getOperatorSessions(), error: null };
  } catch (error) {
    return {
      sessions: null,
      error:
        error instanceof Error
          ? error.message
          : "활성 운영자 세션을 조회할 수 없습니다.",
    };
  }
}

export default async function SecurityStatusPage() {
  const allowed = await requireOperatorPageAccess(
    "/security-status",
    "AUTHENTICATED",
  );

  if (!allowed) {
    return (
      <OperatorAccessDenied
        title="운영 보안 상태"
        requirement="AUTHENTICATED"
      />
    );
  }

  const status = await getOperatorSecurityStatus();
  const authMode = getOperatorAuthMode();
  const canAdminister =
    status?.enabled === false ||
    (status?.authenticated === true && status.role === "ADMIN");
  const sessionResult = await loadSessions(canAdminister);
  const currentSession =
    sessionResult.sessions?.find((session) => session.current) ?? null;

  const rbacValue = !status
    ? "연결 실패"
    : status.enabled
      ? "ENABLED"
      : "LOCAL MODE";
  const identityValue = !status
    ? "확인 불가"
    : status.authenticated
      ? `${status.username ?? "operator"} · ${status.role ?? "UNKNOWN"}`
      : "로그인 필요";
  const activeSessionValue = sessionResult.sessions
    ? `${sessionResult.sessions.length}개`
    : canAdminister
      ? "조회 실패"
      : "ADMIN 전용";
  const idleWindow = currentSession
    ? durationLabel(currentSession.lastSeenAt, currentSession.idleExpiresAt)
    : canAdminister
      ? "활성 세션 없음"
      : "ADMIN 전용";
  const absoluteWindow = currentSession
    ? durationLabel(currentSession.issuedAt, currentSession.expiresAt)
    : canAdminister
      ? "활성 세션 없음"
      : "ADMIN 전용";

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-semibold text-sky-700">
          SECURITY POSTURE
        </p>
        <h1 className="mt-1 text-3xl font-black text-slate-950">
          VisionFlow 운영 보안 상태
        </h1>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">
          RBAC, 브라우저 세션, 만료 정책과 실제 응답 헤더를 한 화면에서
          확인합니다. 운영자 인증 키와 세션 토큰은 수집하거나 표시하지 않습니다.
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatusCard
          label="RBAC"
          value={rbacValue}
          detail={
            status?.enabled
              ? "백엔드 역할 기반 접근 제어가 활성화되어 있습니다."
              : status
                ? "로컬 개발 모드로 역할 제한이 비활성화되어 있습니다."
                : "백엔드 /api/security/me 응답을 확인하세요."
          }
          tone={status?.enabled ? "good" : "warning"}
        />
        <StatusCard
          label="Browser auth mode"
          value={authMode.toUpperCase()}
          detail={
            authMode === "session"
              ? "원본 키 대신 만료형 HttpOnly 브라우저 세션을 사용합니다."
              : "정적 키 전달 모드입니다. 운영 시 session 모드를 권장합니다."
          }
          tone={authMode === "session" ? "good" : "warning"}
        />
        <StatusCard
          label="Current identity"
          value={identityValue}
          detail="현재 요청에 연결된 사용자와 역할입니다."
          tone={status?.authenticated || status?.enabled === false ? "good" : "warning"}
        />
        <StatusCard
          label="Active sessions"
          value={activeSessionValue}
          detail={
            sessionResult.error ??
            (canAdminister
              ? "ADMIN 권한으로 조회한 현재 활성 세션 수입니다."
              : "세션 목록은 ADMIN 로그인 상태에서만 표시됩니다.")
          }
          tone={sessionResult.error ? "warning" : "neutral"}
        />
        <StatusCard
          label="Idle timeout window"
          value={idleWindow}
          detail="현재 세션의 lastSeenAt부터 idleExpiresAt까지 계산한 유휴 만료 구간입니다."
        />
        <StatusCard
          label="Absolute session window"
          value={absoluteWindow}
          detail="현재 세션의 issuedAt부터 expiresAt까지 계산한 절대 만료 구간입니다."
        />
      </section>

      <SecurityHeaderProbe />

      {canAdminister ? (
        <>
          <CspReportMonitor />

          <section className="rounded-2xl border border-amber-200 bg-amber-50 p-6">
            <p className="text-sm font-semibold text-amber-800">DEFERRED CHECKS</p>
            <h2 className="mt-1 text-xl font-black text-slate-950">
              장비 이동 후 이어서 검증할 항목
            </h2>
            <ul className="mt-4 space-y-2 text-sm leading-6 text-amber-950">
              <li>스마트폰 실센서 HTTPS 인증서 검증은 단말 수리 후 재개합니다.</li>
              <li>HP OMEN RTX 5060과 파인튜닝한 best.pt 성능 검증은 장비 이동 후 진행합니다.</li>
              <li>강제 CSP와 HSTS는 HTTPS·AI 배치 주소가 확정된 뒤 적용합니다.</li>
              <li>DJI Mini 4 Pro 전용 연동은 3차 프로젝트 범위로 유지합니다.</li>
            </ul>
            <div className="mt-5 flex flex-wrap gap-3">
              <Link
                href="/operator-sessions"
                className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-bold text-white"
              >
                활성 세션 관리
              </Link>
              <Link
                href="/audit-logs"
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700"
              >
                감사 로그 확인
              </Link>
            </div>
          </section>
        </>
      ) : (
        <section
          data-admin-security-detail-restricted
          className="rounded-2xl border border-slate-200 bg-slate-50 p-6"
        >
          <p className="text-sm font-semibold text-slate-600">
            ADMIN SECURITY DETAIL
          </p>
          <h2 className="mt-1 text-xl font-black text-slate-950">
            상세 보안 관찰 정보는 ADMIN 전용입니다.
          </h2>
          <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-600">
            CSP 위반 URI·source file, 활성 세션 관리, 미완료 hardening 항목은
            ADMIN 로그인 상태에서만 표시됩니다. 현재 역할에는 고수준 RBAC 및
            보안 헤더 상태만 제공합니다.
          </p>
        </section>
      )}
    </div>
  );
}
