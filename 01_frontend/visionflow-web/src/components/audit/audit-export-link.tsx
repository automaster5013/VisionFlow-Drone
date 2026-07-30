"use client";

import { useOperatorAccess } from "@/components/security/operator-access-provider";

interface AuditExportLinkProps {
  href: string;
}

export function AuditExportLink({ href }: AuditExportLinkProps) {
  const { canExportAudit, status } = useOperatorAccess();
  const deniedReason = status
    ? status.role === "INVALID_KEY" || status.role === "INVALID_SESSION"
      ? status.role === "INVALID_SESSION"
        ? "운영자 로그인 세션이 만료되었습니다."
        : "운영자 키가 올바르지 않습니다."
      : "감사 로그를 내보내려면 인증된 운영자 키가 필요합니다."
    : "운영자 권한 상태를 확인할 수 없습니다.";
  const className =
    "rounded-lg border border-emerald-300 bg-emerald-50 px-5 py-2 font-semibold text-emerald-800";

  if (!canExportAudit) {
    return (
      <span
        aria-disabled="true"
        title={deniedReason}
        className={`${className} cursor-not-allowed opacity-50`}
      >
        CSV 내보내기
      </span>
    );
  }

  return (
    <a href={href} download className={`${className} hover:bg-emerald-100`}>
      CSV 내보내기
    </a>
  );
}
