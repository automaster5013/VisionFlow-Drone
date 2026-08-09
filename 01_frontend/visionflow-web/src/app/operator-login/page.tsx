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
          스마트폰은 PC에서 생성한 5분 일회용 QR 로그인을 권장합니다.
          장기 역할 KEY는 초기 설정·복구용으로만 사용하고 브라우저에는 저장하지 않습니다.
        </p>

        <div className="mt-5 rounded-2xl border border-sky-200 bg-sky-50 p-4">
          <p className="text-sm font-bold text-sky-900">
            스마트폰에서 접속 중인가요?
          </p>
          <p className="mt-1 text-xs leading-5 text-sky-800">
            PC의 로그인된 VisionFlow 화면에서 상단의 QR 로그인 버튼을 눌러
            일회용 QR을 생성한 뒤 스마트폰으로 스캔하세요.
          </p>
          <Link
            href="/operator-pair"
            className="mt-3 inline-flex text-sm font-bold text-sky-900 underline underline-offset-4"
          >
            QR 로그인 안내
          </Link>
        </div>

        <details className="mt-5 rounded-2xl border border-slate-200 bg-slate-50 p-4">
          <summary className="cursor-pointer text-sm font-bold text-slate-800">
            비상·초기 설정용 KEY 로그인
          </summary>
          <OperatorLoginForm returnTo={returnTo} />
        </details>

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
