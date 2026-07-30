import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { OperatorLoginForm } from "@/components/security/operator-login-form";
import { getOperatorAuthMode } from "@/lib/server/operator-auth";
import { getOperatorSecurityStatus } from "@/lib/server/operator-security";

export const metadata: Metadata = {
  title: "운영자 로그인",
};

interface OperatorLoginPageProps {
  searchParams: Promise<{ returnTo?: string | string[] }>;
}

function safeReturnTo(value: string | string[] | undefined): string {
  const candidate = Array.isArray(value) ? value[0] : value;
  return candidate?.startsWith("/") && !candidate.startsWith("//")
    ? candidate
    : "/dashboard";
}

export default async function OperatorLoginPage({
  searchParams,
}: OperatorLoginPageProps) {
  const returnTo = safeReturnTo((await searchParams).returnTo);
  const authMode = getOperatorAuthMode();
  const status = await getOperatorSecurityStatus();

  if (authMode !== "session" || status?.enabled === false) {
    redirect(returnTo);
  }
  if (status?.authenticated) {
    redirect(returnTo);
  }

  return (
    <section className="mx-auto max-w-lg py-8 sm:py-16">
      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-xl sm:p-8">
        <p className="text-sm font-bold uppercase tracking-[0.18em] text-sky-700">
          VisionFlow Operator Access
        </p>
        <h1 className="mt-3 text-3xl font-black text-slate-950">
          운영자 로그인
        </h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          발급받은 역할별 키를 입력하세요. 원본 키는 브라우저에 저장하지 않고,
          백엔드가 발급한 만료형 세션만 HttpOnly 쿠키로 보관합니다.
        </p>

        <OperatorLoginForm returnTo={returnTo} />

        <div className="mt-5 border-t border-slate-200 pt-4 text-center">
          <Link
            href="/dashboard"
            className="text-sm font-semibold text-slate-500 hover:text-slate-900"
          >
            조회 전용 대시보드로 돌아가기
          </Link>
        </div>
      </div>
    </section>
  );
}
