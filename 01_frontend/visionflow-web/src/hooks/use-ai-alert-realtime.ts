"use client";

import { useEffect, useRef, useState } from "react";
import { Client, type IMessage } from "@stomp/stompjs";

import { resolveWebSocketUrl } from "@/lib/websocket-url";
import {
    parseAiAlertRealtimeMessage,
    type AiAlertRealtimeConnectionStatus,
    type AiAlertRealtimeMessage,
} from "@/types/ai-alert-realtime";

interface UseAiAlertRealtimeResult {
    connectionStatus: AiAlertRealtimeConnectionStatus;
    lastMessageAt: Date | null;
}

export function useAiAlertRealtime(
    onMessage: (message: AiAlertRealtimeMessage) => void,
): UseAiAlertRealtimeResult {
    const onMessageRef = useRef(onMessage);
    const [connectionStatus, setConnectionStatus] =
        useState<AiAlertRealtimeConnectionStatus>("CONNECTING");
    const [lastMessageAt, setLastMessageAt] = useState<Date | null>(null);

    useEffect(() => {
        onMessageRef.current = onMessage;
    }, [onMessage]);

    useEffect(() => {
        let active = true;

        const client = new Client({
            brokerURL: resolveWebSocketUrl(),
            reconnectDelay: 5_000,
            heartbeatIncoming: 10_000,
            heartbeatOutgoing: 10_000,

            onConnect: () => {
                if (!active) {
                    return;
                }

                setConnectionStatus("CONNECTED");

                client.subscribe("/topic/ai/alerts", (frame: IMessage) => {
                    try {
                        const body: unknown = JSON.parse(frame.body);
                        const message = parseAiAlertRealtimeMessage(body);

                        if (!message) {
                            console.error(
                                "잘못된 AI 경보 실시간 메시지:",
                                body,
                            );
                            return;
                        }

                        onMessageRef.current(message);
                        setLastMessageAt(new Date());
                    } catch (error) {
                        console.error("AI 경보 실시간 메시지 파싱 실패:", error);
                    }
                });
            },

            onStompError: (frame) => {
                if (!active) {
                    return;
                }

                console.error("AI 경보 STOMP 오류:", frame);
                setConnectionStatus("ERROR");
            },

            onWebSocketError: (event) => {
                if (!active) {
                    return;
                }

                console.error("AI 경보 WebSocket 오류:", event);
                setConnectionStatus("ERROR");
            },

            onWebSocketClose: () => {
                if (!active) {
                    return;
                }

                setConnectionStatus("DISCONNECTED");
            },
        });

        client.activate();

        return () => {
            active = false;
            void client.deactivate();
        };
    }, []);

    return {
        connectionStatus,
        lastMessageAt,
    };
}
