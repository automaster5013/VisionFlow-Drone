import type { Metadata } from "next";
import Link from "next/link";

import { OperatorSessionManagementPanel } from "@/components/security/operator-session-management-panel";
import { getOperatorSessions } from "@/lib/server/operator-session-management";
import { getOperatorSecurityStatus } from "@/lib/server/operator-security";
import type { OperatorManagedSession } from "@/types/operator-session-management";

export const metadata: Metadata = {
  title: "운영자 세션 관리",
};

export const dynamic = "force-dynamic";

async function loadSessions(): Promise<{
  data: OperatorManagedSession[];
  error: string | null;
}> {
  try {
    return { data: await getOperatorSessions(), error: null };
  } catch (error) {
    return {
      data: [],
      error:
        error instanceof Error
          ? error.message
          : "활성 운영자 세션을 조회할 수 없습니다.",
    };
  }
}

export default async function OperatorSessionsPage() {
  const status = await getOperatorSecurityStatus();
  const canAdminister = status?.enabled === false || (
    status?.authenticated === true && status.role === "ADMIN"
  );

  if (!canAdminister) {
    return (
      <section className="mx-auto max-w-2xl rounded-2xl border border-amber-200 bg-amber-50 p-6">
        <h1 className="text-2xl font-black text-slate-950">운영자 세션 관리</h1>
        <p className="mt-3 text-sm leading-6 text-amber-900">
          활성 세션 조회와 강제 종료는 ADMIN 권한이 필요합니다. 현재 다른
          역할로 로그인되어 있다면 헤더에서 로그아웃한 뒤 ADMIN으로 다시
          로그인하세요.
        </p>
        {!status?.authenticated ? (
          <Link
            href="/operator-login?returnTo=/operator-sessions"
            className="mt-5 inline-flex rounded-lg bg-slate-950 px-4 py-2 text-sm font-bold text-white"
          >
            ADMIN으로 로그인
          </Link>
        ) : null}
      </section>
    );
  }

  const result = await loadSessions();
  return (
    <div data-operator-sessions-command className="vf-session-command mx-auto max-w-[1500px] space-y-6">
      <header className="vf-session-command__hero">
        <p className="vf-session-command__eyebrow text-sm font-semibold text-sky-700">SECURITY OPERATIONS</p>
        <h1 className="vf-session-command__title mt-1 text-3xl font-bold text-slate-950">
          운영자 활성 세션 관리
        </h1>
        <p className="vf-session-command__lede mt-2 text-sm text-slate-600">
          브라우저에 발급된 세션의 사용 시각과 만료 시각을 확인하고, 분실하거나
          의심되는 세션을 즉시 종료합니다. 원본 키와 세션 토큰은 표시하지 않습니다.
        </p>
      </header>

      {result.error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
          {result.error}
        </div>
      ) : (
        <OperatorSessionManagementPanel initialSessions={result.data} />
      )}
    </div>
  );
}
