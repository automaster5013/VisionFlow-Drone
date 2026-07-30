"use client";

import dynamic from "next/dynamic";

import type { Drone } from "@/types/drone";

const DroneMapClient = dynamic(
    () =>
        import(
            "@/components/drones/map/drone-map-client"
            ),
    {
        ssr: false,
        loading: () => (
            <div className="flex min-h-[420px] items-center justify-center bg-slate-100">
                <div className="text-center">
                    <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-slate-300 border-t-slate-900" />

                    <p className="mt-3 text-sm text-slate-500">
                        지도를 불러오는 중입니다.
                    </p>
                </div>
            </div>
        ),
    },
);

interface DroneLocationMapProps {
    drone: Drone;
}

export function DroneLocationMap({
                                     drone,
                                 }: DroneLocationMapProps) {
    return <DroneMapClient drone={drone} />;
}