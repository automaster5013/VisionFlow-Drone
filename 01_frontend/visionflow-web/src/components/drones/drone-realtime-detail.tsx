"use client";

import { useEffect, useState } from "react";
import { telemetryReception } from "@/lib/telemetry-reception";

import { DroneDetail } from "@/components/drones/drone-detail";
import { RealtimeConnectionBadge } from "@/components/drones/realtime-connection-badge";
import { useDroneTelemetry } from "@/hooks/use-drone-telemetry";
import type { Drone } from "@/types/drone";

interface DroneRealtimeDetailProps {
    initialDrone: Drone;
}

export function DroneRealtimeDetail({
                                        initialDrone,
                                    }: DroneRealtimeDetailProps) {
    const {
        drone,
        connectionStatus,
        lastMessageAt,
    } = useDroneTelemetry(initialDrone);

    const [now, setNow] = useState<number | null>(null);
    useEffect(() => {
        const timer = window.setInterval(() => setNow(Date.now()), 1000);
        return () => window.clearInterval(timer);
    }, []);
    const receivedAt = lastMessageAt?.getTime() ??
        (drone.lastConnectedAt ? new Date(drone.lastConnectedAt).getTime() : null);
    const reception = now === null ? "WAITING" : telemetryReception(now, receivedAt);

    return (
        <div>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <span role="status" className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold">
                    텔레메트리 {reception === "LIVE" ? "수신 중" : reception === "STALE" ? "수신 지연 · 마지막 수신 후 15초 초과 또는 시각 확인 필요" : "수신 시각 확인 중"}
                </span>
                <RealtimeConnectionBadge
                    status={connectionStatus}
                    lastMessageAt={lastMessageAt}
                />
            </div>

            <DroneDetail drone={drone} />
        </div>
    );
}