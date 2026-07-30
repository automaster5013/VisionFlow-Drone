"use client";

import {
    useEffect,
    useState,
} from "react";
import { useRouter } from "next/navigation";

interface DroneAutoRefreshProps {
    intervalMs?: number;
}

export function DroneAutoRefresh({
                                     intervalMs = 5000,
                                 }: DroneAutoRefreshProps) {
    const router = useRouter();

    const [enabled, setEnabled] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [lastRefreshAt, setLastRefreshAt] =
        useState<Date | null>(null);

    useEffect(() => {
        if (!enabled) {
            return;
        }

        const refresh = (): void => {
            // 다른 탭에 있을 때 불필요한 요청을 줄입니다.
            if (document.visibilityState !== "visible") {
                return;
            }

            setRefreshing(true);
            router.refresh();
            setLastRefreshAt(new Date());

            window.setTimeout(() => {
                setRefreshing(false);
            }, 500);
        };

        const intervalId = window.setInterval(
            refresh,
            intervalMs,
        );

        return () => {
            window.clearInterval(intervalId);
        };
    }, [enabled, intervalMs, router]);

    function handleManualRefresh(): void {
        setRefreshing(true);
        router.refresh();
        setLastRefreshAt(new Date());

        window.setTimeout(() => {
            setRefreshing(false);
        }, 500);
    }

    return (
        <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 text-xs text-slate-500">
        <span
            aria-hidden="true"
            className={[
                "h-2 w-2 rounded-full",
                enabled
                    ? "bg-emerald-500"
                    : "bg-slate-400",
            ].join(" ")}
        />

                <span>
          {enabled
              ? `${intervalMs / 1000}초 자동 갱신`
              : "자동 갱신 중지"}
        </span>

                {lastRefreshAt && (
                    <span>
            · 최근{" "}
                        {lastRefreshAt.toLocaleTimeString(
                            "ko-KR",
                        )}
          </span>
                )}
            </div>

            <button
                type="button"
                onClick={handleManualRefresh}
                disabled={refreshing}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
                {refreshing ? "갱신 중..." : "지금 갱신"}
            </button>

            <button
                type="button"
                onClick={() =>
                    setEnabled((current) => !current)
                }
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            >
                {enabled ? "자동 갱신 중지" : "자동 갱신 시작"}
            </button>
        </div>
    );
}