"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import {
    getVisibleNavigationItems,
    isNavigationItemActive,
} from "@/components/layout/navigation-items";
import type { OperatorSecurityStatus } from "@/types/operator-security";

interface AppSidebarProps {
    operatorSecurity: OperatorSecurityStatus | null;
}

function resolveDesktopLinkClassName(
    active: boolean,
    presentation: boolean,
) {
    if (presentation) {
        return [
            "flex items-center gap-3 rounded-xl border px-4 py-3 font-semibold transition",
            active
                ? "border-violet-300 bg-violet-400/25 text-violet-100"
                : "border-violet-400/40 bg-violet-500/10 text-violet-200 hover:bg-violet-500/20",
        ].join(" ");
    }

    return [
        "block rounded-lg border-l-2 px-4 py-3 text-sm font-medium transition-colors",
        active
            ? "border-sky-400 bg-slate-800 text-white"
            : "border-transparent text-slate-300 hover:bg-slate-800 hover:text-white",
    ].join(" ");
}

export function AppSidebar({ operatorSecurity }: AppSidebarProps) {
    const pathname = usePathname();
    const visibleItems = getVisibleNavigationItems(operatorSecurity);

    return (
        <aside className="hidden w-64 shrink-0 border-r border-slate-800 bg-slate-950 lg:block">
            <div className="sticky top-0 flex h-screen flex-col overflow-y-auto p-5">
                <div className="mb-7 rounded-2xl border border-slate-800 bg-slate-900/70 p-4 shadow-inner">
                    <div className="flex items-center gap-3">
                        <span
                            aria-hidden="true"
                            className="grid h-10 w-10 place-items-center rounded-xl bg-sky-500 text-sm font-black text-slate-950 shadow-lg shadow-sky-950/20"
                        >
                            VF
                        </span>
                        <div>
                            <p className="text-[11px] font-black uppercase tracking-[0.22em] text-sky-400">
                                VisionFlow
                            </p>
                            <p className="mt-1 text-base font-black text-white">
                                Mission Control
                            </p>
                        </div>
                    </div>
                    <p className="mt-3 text-xs font-medium leading-5 text-slate-400">
                        Drone · Vision AI Operations
                    </p>
                </div>

                <nav aria-label="주요 메뉴">
                    <p className="px-4 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500">
                        Operations
                    </p>
                    <ul className="mt-3 space-y-1.5">
                        {visibleItems.map((item) => {
                            const active = isNavigationItemActive(
                                pathname,
                                item.href,
                                item.activeAliases,
                            );
                            const presentation = item.presentation === true;

                            return (
                                <li key={item.href} className={presentation ? "pt-2" : undefined}>
                                    <Link
                                        href={item.href}
                                        aria-current={active ? "page" : undefined}
                                        className={resolveDesktopLinkClassName(
                                            active,
                                            presentation,
                                        )}
                                    >
                                        {presentation ? (
                                            <span aria-hidden="true">🎬</span>
                                        ) : null}
                                        <span>{item.label}</span>
                                    </Link>
                                </li>
                            );
                        })}
                    </ul>
                </nav>

                <footer className="mt-auto border-t border-slate-800 pt-5">
                    <p className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">
                        Phase 3 · Edge Operations
                    </p>
                    <p className="mt-2 text-xs font-semibold leading-5 text-slate-400">
                        © 2026 Team PyvaOps.
                        <br />
                        All rights reserved.
                    </p>
                </footer>
            </div>
        </aside>
    );
}
