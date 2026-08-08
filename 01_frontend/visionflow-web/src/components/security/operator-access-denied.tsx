import Link from "next/link";

interface OperatorAccessDeniedProps {
  title: string;
  requirement: "AUTHENTICATED" | "OPERATOR";
}

export function OperatorAccessDenied({
  title,
  requirement,
}: OperatorAccessDeniedProps) {
  const description =
    requirement === "OPERATOR"
      ? "이 화면은 카메라 입력과 AI 운영 경계에 연결되므로 OPERATOR 또는 ADMIN 권한이 필요합니다."
      : "이 화면의 운영 정보를 보려면 유효한 운영자 로그인이 필요합니다.";

  return (
    <section
      role="alert"
      className="mx-auto max-w-2xl rounded-3xl border border-amber-200 bg-amber-50 p-6 shadow-sm sm:p-8"
    >
      <p className="text-xs font-black uppercase tracking-[0.18em] text-amber-700">
        Access restricted
      </p>
      <h1 className="mt-2 text-3xl font-black text-slate-950">{title}</h1>
      <p className="mt-3 text-sm leading-6 text-amber-950">{description}</p>
      <p className="mt-2 text-sm leading-6 text-slate-600">
        현재 역할이 부족하다면 헤더에서 로그아웃한 뒤 승인된 역할로 다시 로그인하세요.
      </p>
      <Link
        href="/dashboard"
        className="mt-6 inline-flex rounded-xl bg-slate-950 px-5 py-3 text-sm font-bold text-white hover:bg-slate-800"
      >
        대시보드로 돌아가기
      </Link>
    </section>
  );
}
