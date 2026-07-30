"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { useAiAlertRealtime } from "@/hooks/use-ai-alert-realtime";
import { formatKoreanDateTime } from "@/lib/date";
import type { AiAlertItem, AiAlertQuery } from "@/types/ai-alert";
import type {
    AiAlertRealtimeAction,
    AiAlertRealtimeConnectionStatus,
    AiAlertRealtimeMessage,
} from "@/types/ai-alert-realtime";

interface AiAlertRealtimeNotifierProps {
    query: AiAlertQuery;
}

interface RecentRealtimeMessage {
    message: AiAlertRealtimeMessage;
    receivedAt: string;
}

type NotificationActivationState =
    | "IDLE"
    | "GRANTED"
    | "DENIED"
    | "UNSUPPORTED";

function matchesQuery(alert: AiAlertItem, query: AiAlertQuery): boolean {
    if (query.droneId !== undefined && alert.droneId !== query.droneId) {
        return false;
    }

    if (query.sessionId && alert.sessionId !== query.sessionId) {
        return false;
    }

    const capturedAt = Date.parse(alert.capturedAt);

    if (query.from && capturedAt < Date.parse(query.from)) {
        return false;
    }

    if (query.to && capturedAt > Date.parse(query.to)) {
        return false;
    }

    return true;
}

function connectionPresentation(
    status: AiAlertRealtimeConnectionStatus,
) {
    return {
        CONNECTING: {
            label: "연결 중",
            className: "bg-sky-100 text-sky-800",
        },
        CONNECTED: {
            label: "실시간 연결",
            className: "bg-emerald-100 text-emerald-800",
        },
        DISCONNECTED: {
            label: "재연결 대기",
            className: "bg-amber-100 text-amber-900",
        },
        ERROR: {
            label: "연결 오류",
            className: "bg-rose-100 text-rose-900",
        },
    }[status];
}

function actionLabel(action: AiAlertRealtimeAction): string {
    return {
        CREATED: "신규 경보",
        ACKNOWLEDGED: "확인 처리",
        RESOLVED: "해결 처리",
    }[action];
}

export function AiAlertRealtimeNotifier({
    query,
}: AiAlertRealtimeNotifierProps) {
    const [recentMessages, setRecentMessages] = useState<
        RecentRealtimeMessage[]
    >([]);
    const [criticalToast, setCriticalToast] = useState<AiAlertItem | null>(null);
    const [notificationActivation, setNotificationActivation] =
        useState<NotificationActivationState>("IDLE");
    const [criticalNotificationEnabled, setCriticalNotificationEnabled] =
        useState(false);
    const audioContextRef = useRef<AudioContext | null>(null);

    const playCriticalTone = useCallback(() => {
        const audioContext = audioContextRef.current;

        if (!audioContext) {
            return;
        }

        const play = () => {
            const startedAt = audioContext.currentTime;

            [0, 0.24].forEach((offset) => {
                const oscillator = audioContext.createOscillator();
                const gain = audioContext.createGain();

                oscillator.type = "sine";
                oscillator.frequency.setValueAtTime(
                    880,
                    startedAt + offset,
                );
                gain.gain.setValueAtTime(0.0001, startedAt + offset);
                gain.gain.exponentialRampToValueAtTime(
                    0.18,
                    startedAt + offset + 0.02,
                );
                gain.gain.exponentialRampToValueAtTime(
                    0.0001,
                    startedAt + offset + 0.18,
                );

                oscillator.connect(gain);
                gain.connect(audioContext.destination);
                oscillator.start(startedAt + offset);
                oscillator.stop(startedAt + offset + 0.2);
            });
        };

        if (audioContext.state === "suspended") {
            void audioContext.resume().then(play);
            return;
        }

        play();
    }, []);

    const handleRealtimeMessage = useCallback(
        (message: AiAlertRealtimeMessage) => {
            if (!matchesQuery(message.alert, query)) {
                return;
            }

            setRecentMessages((current) => {
                const next: RecentRealtimeMessage = {
                    message,
                    receivedAt: new Date().toISOString(),
                };

                return [
                    next,
                    ...current.filter(
                        (item) => item.message.alert.id !== message.alert.id,
                    ),
                ].slice(0, 5);
            });

            if (
                message.action !== "CREATED" ||
                message.alert.severity !== "CRITICAL" ||
                message.alert.status !== "OPEN"
            ) {
                return;
            }

            setCriticalToast(message.alert);

            if (!criticalNotificationEnabled) {
                return;
            }

            playCriticalTone();

            if (
                typeof Notification !== "undefined" &&
                Notification.permission === "granted"
            ) {
                const notification = new Notification(
                    "VisionFlow 긴급 AI 탐지",
                    {
                        body: `드론 #${message.alert.droneId} · ${message.alert.title} · ${message.alert.summary}`,
                        tag: `visionflow-ai-alert-${message.alert.id}`,
                    },
                );

                notification.onclick = () => {
                    window.focus();
                    window.location.hash = "ai-alert-operations";
                    notification.close();
                };
            }
        },
        [criticalNotificationEnabled, playCriticalTone, query],
    );

    const { connectionStatus, lastMessageAt } =
        useAiAlertRealtime(handleRealtimeMessage);
    const connection = connectionPresentation(connectionStatus);

    useEffect(() => {
        if (!criticalToast) {
            return;
        }

        const timeoutId = window.setTimeout(() => {
            setCriticalToast(null);
        }, 10_000);

        return () => window.clearTimeout(timeoutId);
    }, [criticalToast]);

    useEffect(
        () => () => {
            const audioContext = audioContextRef.current;

            if (audioContext) {
                void audioContext.close();
            }
        },
        [],
    );

    async function enableCriticalNotifications() {
        try {
            if (!audioContextRef.current) {
                audioContextRef.current = new AudioContext();
            }

            if (audioContextRef.current.state === "suspended") {
                await audioContextRef.current.resume();
            }
        } catch (error) {
            console.error("긴급 경보 알림음 초기화 실패:", error);
        }

        setCriticalNotificationEnabled(true);

        if (typeof Notification === "undefined") {
            setNotificationActivation("UNSUPPORTED");
            return;
        }

        try {
            const permission =
                Notification.permission === "default"
                    ? await Notification.requestPermission()
                    : Notification.permission;

            setNotificationActivation(
                permission === "granted" ? "GRANTED" : "DENIED",
            );
        } catch (error) {
            console.error("브라우저 알림 권한 요청 실패:", error);
            setNotificationActivation("DENIED");
        }
    }

    return (
        <section
            aria-labelledby="ai-alert-realtime-title"
            className="rounded-2xl border border-cyan-200 bg-cyan-50/40 p-4 shadow-sm"
        >
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <div className="flex flex-wrap items-center gap-2">
                        <h2
                            id="ai-alert-realtime-title"
                            className="font-bold text-slate-950"
                        >
                            AI 경보 실시간 채널
                        </h2>
                        <span
                            className={`rounded-full px-2.5 py-1 text-xs font-bold ${connection.className}`}
                        >
                            {connection.label}
                        </span>
                        {criticalNotificationEnabled && (
                            <span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-bold text-violet-800">
                                긴급 알림 활성
                            </span>
                        )}
                    </div>
                    <p className="mt-1 text-xs text-slate-600">
                        STOMP `/topic/ai/alerts` · 마지막 수신 {lastMessageAt ? formatKoreanDateTime(lastMessageAt.toISOString()) : "-"}
                    </p>
                </div>

                <button
                    type="button"
                    onClick={() => void enableCriticalNotifications()}
                    disabled={criticalNotificationEnabled}
                    className="rounded-lg bg-violet-700 px-4 py-2 text-sm font-bold text-white hover:bg-violet-600 disabled:cursor-default disabled:bg-violet-300"
                >
                    {criticalNotificationEnabled
                        ? "긴급 알림 켜짐"
                        : "알림음·브라우저 알림 켜기"}
                </button>
            </div>

            {notificationActivation === "DENIED" && (
                <p className="mt-2 text-xs font-medium text-amber-800">
                    브라우저 알림 권한은 거부됐지만 화면 토스트와 알림음은 사용할 수 있습니다.
                </p>
            )}

            {notificationActivation === "UNSUPPORTED" && (
                <p className="mt-2 text-xs font-medium text-amber-800">
                    이 브라우저는 시스템 알림을 지원하지 않습니다. 화면 토스트와 알림음을 사용합니다.
                </p>
            )}

            {recentMessages.length > 0 && (
                <div className="mt-3 grid gap-2 lg:grid-cols-2">
                    {recentMessages.slice(0, 4).map(({ message, receivedAt }) => (
                        <div
                            key={`${message.alert.id}-${message.action}`}
                            className="flex items-start justify-between gap-3 rounded-lg border border-cyan-100 bg-white px-3 py-2 text-xs"
                        >
                            <div className="min-w-0">
                                <div className="font-bold text-slate-900">
                                    {actionLabel(message.action)} · 경보 #{message.alert.id}
                                </div>
                                <div className="mt-0.5 truncate text-slate-600">
                                    드론 #{message.alert.droneId} · {message.alert.title}
                                </div>
                            </div>
                            <time className="shrink-0 text-slate-400">
                                {new Date(receivedAt).toLocaleTimeString("ko-KR")}
                            </time>
                        </div>
                    ))}
                </div>
            )}

            {criticalToast && (
                <div
                    className="fixed bottom-5 right-5 z-[60] w-[min(26rem,calc(100vw-2.5rem))] rounded-2xl border-2 border-rose-400 bg-rose-950 p-5 text-white shadow-2xl"
                    role="alert"
                    aria-live="assertive"
                >
                    <div className="flex items-start justify-between gap-3">
                        <div>
                            <div className="text-xs font-bold uppercase tracking-widest text-rose-200">
                                Critical AI Alert
                            </div>
                            <div className="mt-2 text-lg font-bold">
                                {criticalToast.title}
                            </div>
                        </div>
                        <button
                            type="button"
                            onClick={() => setCriticalToast(null)}
                            aria-label="긴급 경보 닫기"
                            className="rounded-lg border border-rose-300/60 px-2 py-1 text-xs font-bold text-rose-100"
                        >
                            닫기
                        </button>
                    </div>

                    <p className="mt-2 text-sm text-rose-100">
                        드론 #{criticalToast.droneId} · {criticalToast.summary}
                    </p>

                    <div className="mt-4 flex flex-wrap justify-end gap-2">
                        <Link
                            href={`/drones?droneId=${criticalToast.droneId}&sessionId=${encodeURIComponent(criticalToast.sessionId)}#flight-session-replay`}
                            className="rounded-lg border border-rose-200/60 px-3 py-2 text-xs font-bold text-white hover:bg-rose-900"
                        >
                            비행 경로
                        </Link>
                        <a
                            href="#ai-alert-operations"
                            onClick={() => setCriticalToast(null)}
                            className="rounded-lg bg-white px-3 py-2 text-xs font-bold text-rose-950"
                        >
                            경보 관제 열기
                        </a>
                    </div>
                </div>
            )}
        </section>
    );
}
