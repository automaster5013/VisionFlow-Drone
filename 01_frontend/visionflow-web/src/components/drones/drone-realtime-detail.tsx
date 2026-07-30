"use client";

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

    return (
        <div>
            <div className="mb-4 flex justify-end">
                <RealtimeConnectionBadge
                    status={connectionStatus}
                    lastMessageAt={lastMessageAt}
                />
            </div>

            <DroneDetail drone={drone} />
        </div>
    );
}