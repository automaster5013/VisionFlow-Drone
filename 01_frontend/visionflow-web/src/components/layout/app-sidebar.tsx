import Link from "next/link";

import type { OperatorSecurityStatus } from "@/types/operator-security";

const navigationItems = [
    {
        label: "대시보드",
        href: "/dashboard",
    },
    {
        label: "드론 관리",
        href: "/drones",
    },
    {
        label: "카메라",
        href: "/cameras",
    },
    {
        label: "이벤트",
        href: "/events",
    },
    {
        label: "감사 로그",
        href: "/audit-logs",
    },
    {
        label: "보안 상태",
        href: "/security-status",
    },
    {
        label: "세션 관리",
        href: "/operator-sessions",
        adminOnly: true,
    },
    {
        label: "통계",
        href: "/statistics",
    },
    {
        label: "AI 모델",
        href: "/models",
    },
    {
        label: "설정",
        href: "/settings",
    },
];

interface AppSidebarProps {
    operatorSecurity: OperatorSecurityStatus | null;
}

export function AppSidebar({ operatorSecurity }: AppSidebarProps) {
    const canAdminister = operatorSecurity?.enabled === false || (
        operatorSecurity?.authenticated === true &&
        operatorSecurity.role === "ADMIN"
    );
    const visibleItems = navigationItems.filter(
        (item) => !item.adminOnly || canAdminister,
    );

    return (
        <aside className="hidden w-64 shrink-0 border-r border-slate-800 bg-slate-950 lg:block">
            <div className="sticky top-0 flex h-screen flex-col overflow-y-auto p-5">
                <div className="mb-8">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-400">
                        VisionFlow
                    </p>

                    <p className="mt-2 text-lg font-bold text-white">Drone Control</p>
                </div>

                <nav aria-label="주요 메뉴">
                    <ul className="space-y-2">
                        {visibleItems.map((item) => (
                            <li key={item.href}>
                                <Link
                                    href={item.href}
                                    className={[
                                        "block rounded-lg px-4 py-3 text-sm font-medium",
                                        "text-slate-300 transition-colors",
                                        "hover:bg-slate-800 hover:text-white",
                                    ].join(" ")}
                                >
                                    {item.label}
                                </Link>
                            </li>
                        ))}
                    </ul>
                
      {/* VISIONFLOW_PRESENTATION_DEMO_MODE_LINK */}
      <Link
        href="/demo-mode"
        className="mt-2 flex items-center gap-3 rounded-xl border border-violet-400/40 bg-violet-500/10 px-4 py-3 font-semibold text-violet-700 transition hover:bg-violet-500/20 dark:text-violet-200"
      >
        <span aria-hidden="true">🎬</span>
        <span>시연 모드</span>
      </Link>
</nav>

                <footer className="mt-auto border-t border-slate-800 pt-5">
                    <p className="text-xs font-semibold leading-5 text-slate-400">
                        © 2026 Team PyvaOps.
                        <br />
                        All rights reserved.
                    </p>
                </footer>
            </div>
        </aside>
    );
}
