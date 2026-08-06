"use client";

import { useEffect, useRef, useState } from "react";
import { Client, type IMessage } from "@stomp/stompjs";

import { resolveWebSocketUrl } from "@/lib/websocket-url";
import {
    parseIncidentRealtimeMessage,
    type IncidentRealtimeConnectionStatus,
    type IncidentRealtimeMessage,
} from "@/types/incident-realtime";

interface UseIncidentRealtimeResult {
    connectionStatus: IncidentRealtimeConnectionStatus;
    lastMessageAt: Date | null;
}

export function useIncidentRealtime(
    onMessage: (message: IncidentRealtimeMessage) => void,
): UseIncidentRealtimeResult {
    const onMessageRef = useRef(onMessage);
    const [connectionStatus, setConnectionStatus] =
        useState<IncidentRealtimeConnectionStatus>("CONNECTING");
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
                if (!active) return;
                setConnectionStatus("CONNECTED");

                client.subscribe("/topic/incidents", (frame: IMessage) => {
                    try {
                        const body: unknown = JSON.parse(frame.body);
                        const message = parseIncidentRealtimeMessage(body);

                        if (!message) {
                            console.error(
                                "잘못된 Incident 실시간 메시지:",
                                body,
                            );
                            return;
                        }

                        onMessageRef.current(message);
                        setLastMessageAt(new Date());
                    } catch (error) {
                        console.error(
                            "Incident 실시간 메시지 파싱 실패:",
                            error,
                        );
                    }
                });
            },

            onStompError: (frame) => {
                if (!active) return;
                console.error("Incident STOMP 오류:", frame);
                setConnectionStatus("ERROR");
            },

            onWebSocketError: (event) => {
                if (!active) return;
                console.error("Incident WebSocket 오류:", event);
                setConnectionStatus("ERROR");
            },

            onWebSocketClose: () => {
                if (!active) return;
                setConnectionStatus("DISCONNECTED");
            },
        });

        client.activate();

        return () => {
            active = false;
            void client.deactivate();
        };
    }, []);

    return { connectionStatus, lastMessageAt };
}
