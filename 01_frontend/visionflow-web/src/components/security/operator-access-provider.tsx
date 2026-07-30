"use client";

import {
  createContext,
  useContext,
  useMemo,
  type ReactNode,
} from "react";

import type { OperatorSecurityStatus } from "@/types/operator-security";

interface OperatorAccess {
  status: OperatorSecurityStatus | null;
  canOperate: boolean;
  canAdminister: boolean;
  canExportAudit: boolean;
  operateDeniedReason: string | null;
  adminDeniedReason: string | null;
}

const unavailableReason =
  "운영자 권한 상태를 확인할 수 없어 변경 기능을 잠갔습니다.";

const OperatorAccessContext = createContext<OperatorAccess>({
  status: null,
  canOperate: false,
  canAdminister: false,
  canExportAudit: false,
  operateDeniedReason: unavailableReason,
  adminDeniedReason: unavailableReason,
});

interface OperatorAccessProviderProps {
  status: OperatorSecurityStatus | null;
  children: ReactNode;
}

export function OperatorAccessProvider({
  status,
  children,
}: OperatorAccessProviderProps) {
  const access = useMemo<OperatorAccess>(() => {
    if (!status) {
      return {
        status,
        canOperate: false,
        canAdminister: false,
        canExportAudit: false,
        operateDeniedReason: unavailableReason,
        adminDeniedReason: unavailableReason,
      };
    }

    if (!status.enabled) {
      return {
        status,
        canOperate: true,
        canAdminister: true,
        canExportAudit: true,
        operateDeniedReason: null,
        adminDeniedReason: null,
      };
    }

    const authenticated = status.authenticated;
    const canOperate =
      authenticated && (status.role === "OPERATOR" || status.role === "ADMIN");
    const canAdminister = authenticated && status.role === "ADMIN";
    const authenticationReason =
      status.role === "INVALID_KEY" || status.role === "INVALID_SESSION"
        ? status.role === "INVALID_SESSION"
          ? "운영자 로그인 세션이 만료되었습니다."
          : "운영자 키가 올바르지 않습니다."
        : "운영자 인증 키가 필요합니다.";

    return {
      status,
      canOperate,
      canAdminister,
      canExportAudit: authenticated,
      operateDeniedReason: canOperate
        ? null
        : authenticated
          ? "OPERATOR 이상의 권한이 필요한 기능입니다."
          : authenticationReason,
      adminDeniedReason: canAdminister
        ? null
        : authenticated
          ? "ADMIN 권한이 필요한 기능입니다."
          : authenticationReason,
    };
  }, [status]);

  return (
    <OperatorAccessContext.Provider value={access}>
      {children}
    </OperatorAccessContext.Provider>
  );
}

export function useOperatorAccess(): OperatorAccess {
  return useContext(OperatorAccessContext);
}
