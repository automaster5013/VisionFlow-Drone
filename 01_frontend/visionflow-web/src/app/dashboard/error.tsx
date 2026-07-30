"use client";

import { useEffect } from "react";

interface DashboardErrorProps {
    error: Error & {
        digest?: string;
    };
    reset: () => void;
}

export default function DashboardError({
                                           error,
                                           reset,
                                       }: DashboardErrorProps) {
    useEffect(() => {
        console.error("Dashboard error:", error);
    }, [error]);

    return (
        <section className="rounded-2xl border border-red-200 bg-white p-8 shadow-sm">
            <p className="text-sm font-semibold uppercase tracking-wider text-red-600">
                Connection Error
            </p>

            <h1 className="mt-2 text-2xl font-bold text-slate-950">
                백엔드 상태를 확인할 수 없습니다.
            </h1>

            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
                Spring Boot 서버 또는 MySQL 컨테이너가 실행 중인지 확인한 후 다시
                시도하세요.
            </p>

            {process.env.NODE_ENV === "development" && (
                <pre className="mt-5 overflow-x-auto rounded-xl bg-slate-950 p-4 text-xs leading-6 text-slate-200">
          {error.message}
        </pre>
            )}

            <button
                type="button"
                onClick={reset}
                className={[
                    "mt-6 rounded-lg bg-slate-900 px-5 py-3",
                    "text-sm font-semibold text-white",
                    "transition-colors hover:bg-slate-700",
                    "focus:outline-none focus:ring-2 focus:ring-slate-500",
                    "focus:ring-offset-2",
                ].join(" ")}
            >
                다시 확인
            </button>
        </section>
    );
}