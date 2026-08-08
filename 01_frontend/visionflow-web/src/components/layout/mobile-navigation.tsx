"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
    useCallback,
    useEffect,
    useId,
    useRef,
    useState,
} from "react";

import {
    getVisibleNavigationItems,
    isNavigationItemActive,
} from "@/components/layout/navigation-items";
import type { OperatorSecurityStatus } from "@/types/operator-security";

interface MobileNavigationProps {
    operatorSecurity: OperatorSecurityStatus | null;
}

export function MobileNavigation({ operatorSecurity }: MobileNavigationProps) {
    const pathname = usePathname();
    const panelId = useId();
    const openerRef = useRef<HTMLButtonElement>(null);
    const closeButtonRef = useRef<HTMLButtonElement>(null);
    const panelRef = useRef<HTMLElement>(null);
    const [open, setOpen] = useState(false);
    const visibleItems = getVisibleNavigationItems(operatorSecurity);

    const closeMenu = useCallback((restoreFocus: boolean) => {
        setOpen(false);
        if (restoreFocus) {
            window.requestAnimationFrame(() => openerRef.current?.focus());
        }
    }, []);

    useEffect(() => {
        if (!open) {
            return;
        }

        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        closeButtonRef.current?.focus();

        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === "Escape") {
                event.preventDefault();
                closeMenu(true);
                return;
            }

            if (event.key === "Tab") {
                const focusable = panelRef.current?.querySelectorAll<HTMLElement>(
                    'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
                );
                if (!focusable || focusable.length === 0) {
                    event.preventDefault();
                    return;
                }

                const first = focusable[0];
                const last = focusable[focusable.length - 1];
                if (event.shiftKey && document.activeElement === first) {
                    event.preventDefault();
                    last.focus();
                } else if (!event.shiftKey && document.activeElement === last) {
                    event.preventDefault();
                    first.focus();
                }
            }
        }

        document.addEventListener("keydown", handleKeyDown);
        return () => {
            document.body.style.overflow = previousOverflow;
            document.removeEventListener("keydown", handleKeyDown);
        };
    }, [closeMenu, open]);

    return (
        <div className="lg:hidden">
            <button
                ref={openerRef}
                type="button"
                aria-expanded={open}
                aria-controls={panelId}
                aria-label="주요 메뉴 열기"
                onClick={() => setOpen(true)}
                className="inline-flex min-h-10 items-center rounded-lg border border-slate-200 px-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-500"
            >
                메뉴
            </button>

            {open ? (
                <div className="fixed inset-0 z-50 lg:hidden">
                    <button
                        type="button"
                        aria-label="주요 메뉴 닫기"
                        onClick={() => closeMenu(true)}
                        className="absolute inset-0 bg-slate-950/70"
                    />

                    <aside
                        ref={panelRef}
                        id={panelId}
                        role="dialog"
                        aria-modal="true"
                        aria-label="모바일 주요 메뉴"
                        className="relative flex h-full w-[min(20rem,88vw)] flex-col overflow-y-auto border-r border-slate-800 bg-slate-950 p-5 shadow-2xl"
                    >
                        <div className="mb-7 flex items-start justify-between gap-4">
                            <div>
                                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-400">
                                    VisionFlow
                                </p>
                                <p className="mt-2 text-lg font-bold text-white">
                                    Drone Control
                                </p>
                            </div>

                            <button
                                ref={closeButtonRef}
                                type="button"
                                aria-label="주요 메뉴 닫기"
                                onClick={() => closeMenu(true)}
                                className="min-h-10 rounded-lg border border-slate-700 px-3 text-sm font-semibold text-slate-200 hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400"
                            >
                                닫기
                            </button>
                        </div>

                        <nav aria-label="모바일 주요 메뉴">
                            <ul className="space-y-2">
                                {visibleItems.map((item) => {
                                    const active = isNavigationItemActive(
                                        pathname,
                                        item.href,
                                    );
                                    const presentation = item.presentation === true;

                                    return (
                                        <li
                                            key={item.href}
                                            className={presentation ? "pt-2" : undefined}
                                        >
                                            <Link
                                                href={item.href}
                                                aria-current={active ? "page" : undefined}
                                                onClick={() => closeMenu(false)}
                                                className={[
                                                    "flex min-h-11 items-center gap-3 rounded-lg border px-4 py-3 text-sm font-semibold transition-colors",
                                                    presentation
                                                        ? active
                                                            ? "border-violet-300 bg-violet-400/25 text-violet-100"
                                                            : "border-violet-400/40 bg-violet-500/10 text-violet-200 hover:bg-violet-500/20"
                                                        : active
                                                            ? "border-sky-400 bg-slate-800 text-white"
                                                            : "border-transparent text-slate-300 hover:bg-slate-800 hover:text-white",
                                                ].join(" ")}
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

                        <p className="mt-auto border-t border-slate-800 pt-5 text-xs font-semibold leading-5 text-slate-400">
                            © 2026 Team PyvaOps.
                            <br />
                            All rights reserved.
                        </p>
                    </aside>
                </div>
            ) : null}
        </div>
    );
}
