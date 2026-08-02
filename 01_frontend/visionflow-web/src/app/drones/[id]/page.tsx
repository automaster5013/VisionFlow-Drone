import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";

import { DroneRealtimeDetail } from "@/components/drones/drone-realtime-detail";
import { getDrone } from "@/lib/api/drones";
import type { Drone } from "@/types/drone";

interface DroneDetailPageProps {
    params: Promise<{
        id: string;
    }>;
}

export const metadata: Metadata = {
    title: "드론 상세",
};

export const dynamic = "force-dynamic";

export default async function DroneDetailPage({
                                                  params,
                                              }: DroneDetailPageProps) {
    const { id } = await params;

    if (!/^\d+$/.test(id)) {
        notFound();
    }

    let drone: Drone;

    try {
        drone = await getDrone(id);
    } catch (error) {
        if (
            error instanceof Error &&
            error.message === "DRONE_NOT_FOUND"
        ) {
            notFound();
        }

        if (
            error instanceof Error &&
            error.message === "OPERATOR_AUTHENTICATION_REQUIRED"
        ) {
            redirect(
                `/operator-login?returnTo=${encodeURIComponent(`/drones/${id}`)}`,
            );
        }

        throw error;
    }

    return (
        <DroneRealtimeDetail
            initialDrone={drone}
        />
    );
}
