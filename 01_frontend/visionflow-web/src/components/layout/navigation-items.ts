import type { OperatorSecurityStatus } from "@/types/operator-security";

export interface AppNavigationItem {
    label: string;
    href: string;
    adminOnly?: boolean;
    presentation?: boolean;
    activeAliases?: string[];
}

export const appNavigationItems: AppNavigationItem[] = [
    { label: "대시보드", href: "/dashboard" },
    { label: "드론 관리", href: "/drones" },
    {
        label: "카메라",
        href: "/cameras",
        activeAliases: ["/mobile-camera"],
    },
    { label: "이벤트", href: "/events" },
    { label: "감사 로그", href: "/audit-logs" },
    { label: "보안 상태", href: "/security-status" },
    {
        label: "세션 관리",
        href: "/operator-sessions",
        adminOnly: true,
    },
    { label: "통계", href: "/statistics" },
    { label: "AI 모델", href: "/models" },
    { label: "설정", href: "/settings" },
    {
        label: "시연 모드",
        href: "/demo-mode",
        presentation: true,
    },
];

export function canAdministerOperatorSessions(
    operatorSecurity: OperatorSecurityStatus | null,
) {
    return operatorSecurity?.enabled === false || (
        operatorSecurity?.authenticated === true &&
        operatorSecurity.role === "ADMIN"
    );
}

export function getVisibleNavigationItems(
    operatorSecurity: OperatorSecurityStatus | null,
) {
    const canAdminister = canAdministerOperatorSessions(operatorSecurity);

    return appNavigationItems.filter(
        (item) => !item.adminOnly || canAdminister,
    );
}

function matchesNavigationPath(pathname: string, href: string) {
    if (href === "/dashboard") {
        return pathname === "/" || pathname === href;
    }

    return pathname === href || pathname.startsWith(`${href}/`);
}

export function isNavigationItemActive(
    pathname: string,
    href: string,
    activeAliases: readonly string[] = [],
) {
    return [href, ...activeAliases].some((candidate) =>
        matchesNavigationPath(pathname, candidate),
    );
}
