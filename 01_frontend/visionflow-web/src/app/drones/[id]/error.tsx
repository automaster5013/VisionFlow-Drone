"use client";

import { useEffect } from "react";

interface DroneDetailErrorProps {
    error: Error & {
        digest?: string;
    };
    reset: () => void;
}

export default function DroneDetailError({
                                             error,
                                             reset,
                                         }: DroneDetailErrorProps) {
    useEffect(() => {
        console.error(
            "Drone detail page error:",
            error,
        );
    }, [error]);

    return (
        <section className="rounded-2xl border border-red-200 bg-white p-8 shadow-sm">
            <p className="text-sm font-semibold uppercase tracking-wider text-red-600">
                Drone Detail Error
            </p>

            <h1 className="mt-2 text-2xl font-bold text-slate-950">
                드론 상세 정보를 불러올 수 없습니다.
            </h1>

            <p className="mt-3 text-sm leading-6 text-slate-600">
                Spring Boot 서버, MySQL 연결과 드론 ID를
                확인하세요.
            </p>

            {process.env.NODE_ENV ===
                "development" && (
                    <pre className="mt-5 overflow-x-auto rounded-xl bg-slate-950 p-4 text-xs leading-6 text-slate-200">
          {error.message}
        </pre>
                )}

            <button
                type="button"
                onClick={reset}
                className="mt-6 rounded-lg bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-700"
            >
                다시 조회
            </button>
        </section>
    );
}