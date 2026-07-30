"use client";

import {
    useEffect,
    useRef,
    useState,
} from "react";
import {
    Client,
    type IMessage,
} from "@stomp/stompjs";

import type { Drone } from "@/types/drone";
import type { WebSocketConnectionStatus } from "@/types/websocket";

interface UseDroneTelemetryResult {
    drone: Drone;
    connectionStatus: WebSocketConnectionStatus;
    lastMessageAt: Date | null;
}

interface RealtimeDroneState {
    droneId: number;
    drone: Drone;
}

export function useDroneTelemetry(
    initialDrone: Drone,
): UseDroneTelemetryResult {
    const [realtimeState, setRealtimeState] =
        useState<RealtimeDroneState | null>(null);

    const [connectionStatus, setConnectionStatus] =
        useState<WebSocketConnectionStatus>(
            "CONNECTING",
        );

    const [lastMessageAt, setLastMessageAt] =
        useState<Date | null>(null);

    const clientRef = useRef<Client | null>(null);

    useEffect(() => {
        const websocketUrl =
            process.env.NEXT_PUBLIC_WEBSOCKET_URL ??
            "ws://localhost:8080/ws";

        const client = new Client({
            brokerURL: websocketUrl,
            reconnectDelay: 5000,
            heartbeatIncoming: 10000,
            heartbeatOutgoing: 10000,
            connectionTimeout: 8000,

            debug:
                process.env.NODE_ENV === "development"
                    ? (message: string) => {
                        console.debug("[STOMP]", message);
                    }
                    : () => undefined,
        });

        client.onConnect = () => {
            setConnectionStatus("CONNECTED");

            client.subscribe(
                `/topic/drones/${initialDrone.id}/telemetry`,
                (message: IMessage) => {
                    try {
                        const telemetry = JSON.parse(
                            message.body,
                        ) as Drone;

                        setRealtimeState({
                            droneId: telemetry.id,
                            drone: telemetry,
                        });

                        setLastMessageAt(new Date());
                    } catch (error) {
                        console.error(
                            "WebSocket 텔레메트리 파싱 실패:",
                            error,
                        );
                    }
                },
            );
        };

        client.onWebSocketClose = () => {
            setConnectionStatus("DISCONNECTED");
        };

        client.onWebSocketError = (event) => {
            console.error(
                "WebSocket connection error:",
                event,
            );

            setConnectionStatus("ERROR");
        };

        client.onStompError = (frame) => {
            console.error(
                "STOMP broker error:",
                frame.headers.message,
                frame.body,
            );

            setConnectionStatus("ERROR");
        };

        client.activate();
        clientRef.current = client;

        return () => {
            clientRef.current = null;
            void client.deactivate();
        };
    }, [initialDrone.id]);

    const drone =
        realtimeState?.droneId === initialDrone.id
            ? realtimeState.drone
            : initialDrone;

    return {
        drone,
        connectionStatus,
        lastMessageAt,
    };
}