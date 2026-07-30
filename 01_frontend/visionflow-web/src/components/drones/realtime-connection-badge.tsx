"use client";

import type { WebSocketConnectionStatus } from "@/types/websocket";

interface RealtimeConnectionBadgeProps {
    status: WebSocketConnectionStatus;
    lastMessageAt: Date | null;
}

const statusConfig: Record<
    WebSocketConnectionStatus,
    {
        label: string;
        className: string;
        dotClassName: string;
    }
> = {
    CONNECTING: {
        label: "실시간 연결 중",
        className:
            "border-amber-200 bg-amber-50 text-amber-700",
        dotClassName: "bg-amber-500 animate-pulse",
    },

    CONNECTED: {
        label: "실시간 연결됨",
        className:
            "border-emerald-200 bg-emerald-50 text-emerald-700",
        dotClassName: "bg-emerald-500",
    },

    DISCONNECTED: {
        label: "연결 끊김",
        className:
            "border-slate-200 bg-slate-100 text-slate-600",
        dotClassName: "bg-slate-400",
    },

    ERROR: {
        label: "연결 오류",
        className:
            "border-red-200 bg-red-50 text-red-700",
        dotClassName: "bg-red-500",
    },
};

export function RealtimeConnectionBadge({
                                            status,
                                            lastMessageAt,
                                        }: RealtimeConnectionBadgeProps) {
    const config = statusConfig[status];

    return (
        <div className="flex flex-wrap items-center justify-end gap-2">
      <span
          className={[
              "inline-flex items-center gap-2 rounded-full border",
              "px-3 py-1 text-xs font-semibold",
              config.className,
          ].join(" ")}
      >
        <span
            aria-hidden="true"
            className={[
                "h-2 w-2 rounded-full",
                config.dotClassName,
            ].join(" ")}
        />

          {config.label}
      </span>

            {lastMessageAt && (
                <span className="text-xs text-slate-500">
          최근 수신{" "}
                    {lastMessageAt.toLocaleTimeString(
                        "ko-KR",
                    )}
        </span>
            )}
        </div>
    );
}