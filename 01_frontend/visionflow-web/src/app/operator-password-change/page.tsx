import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { OperatorPasswordChangeForm } from "@/components/security/operator-password-change-form";
import { getOperatorAuthMode } from "@/lib/server/operator-auth";
import { getOperatorSecurityStatus } from "@/lib/server/operator-security";

export const metadata: Metadata = {
  title: "초기 비밀번호 변경",
};

interface OperatorPasswordChangePageProps {
  searchParams: Promise<{ returnTo?: string | string[] }>;
}

function safeReturnTo(value: string | string[] | undefined): string {
  const candidate = Array.isArray(value) ? value[0] : value;
  return candidate?.startsWith("/") && !candidate.startsWith("//")
    ? candidate
    : "/dashboard";
}

export default async function OperatorPasswordChangePage({
  searchParams,
}: OperatorPasswordChangePageProps) {
  const returnTo = safeReturnTo((await searchParams).returnTo);
  const status = await getOperatorSecurityStatus();
  if (getOperatorAuthMode() !== "session" || status?.enabled === false) {
    redirect(returnTo);
  }
  if (!status?.authenticated) {
    redirect(`/operator-login?returnTo=${encodeURIComponent(returnTo)}`);
  }

  return (
    <section className="mx-auto max-w-lg py-8 sm:py-16">
      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-xl sm:p-8">
        <p className="text-sm font-bold uppercase tracking-[0.18em] text-sky-700">
          VisionFlow First Sign-in
        </p>
        <h1 className="mt-3 text-3xl font-black text-slate-950">
          초기 비밀번호 변경
        </h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          자동 생성된 임시 비밀번호는 최초 로그인에만 사용됩니다. 새 비밀번호를
          저장하면 기존 임시 비밀번호는 즉시 무효화됩니다.
        </p>
        <OperatorPasswordChangeForm returnTo={returnTo} />
      </div>
    </section>
  );
}
