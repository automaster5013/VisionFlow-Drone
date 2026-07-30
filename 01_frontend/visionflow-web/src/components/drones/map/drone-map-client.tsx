"use client";

import {
    Circle,
    MapContainer,
    Marker,
    Popup,
    TileLayer,
} from "react-leaflet";
import L from "leaflet";

import { MapPositionController } from "@/components/drones/map/map-position-controller";
import type { Drone } from "@/types/drone";

interface DroneMapClientProps {
    drone: Drone;
}

/*
 * Next.js 번들 환경에서는 Leaflet 기본 마커 이미지 경로가
 * 정상적으로 해석되지 않는 경우가 있으므로 마커를 직접 지정합니다.
 */
const droneIcon = L.divIcon({
    className: "visionflow-drone-marker",
    html: `
    <div style="
      width: 36px;
      height: 36px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 9999px;
      border: 3px solid white;
      background: #0f172a;
      box-shadow: 0 4px 12px rgba(15, 23, 42, 0.35);
      font-size: 18px;
    ">
      ✈
    </div>
  `,
    iconSize: [36, 36],
    iconAnchor: [18, 18],
    popupAnchor: [0, -22],
});

export default function DroneMapClient({
                                           drone,
                                       }: DroneMapClientProps) {
    if (
        drone.latitude === null ||
        drone.longitude === null
    ) {
        return (
            <div className="flex min-h-[420px] items-center justify-center bg-slate-100 p-8 text-center">
                <div>
                    <p className="text-lg font-bold text-slate-800">
                        위치 정보가 없습니다.
                    </p>

                    <p className="mt-2 text-sm leading-6 text-slate-500">
                        텔레메트리 API로 위도와 경도를
                        전송하면 지도에 위치가 표시됩니다.
                    </p>
                </div>
            </div>
        );
    }

    const position: [number, number] = [
        drone.latitude,
        drone.longitude,
    ];

    return (
        <MapContainer
            center={position}
            zoom={16}
            scrollWheelZoom
            className="min-h-[420px] w-full"
        >
            <TileLayer
                attribution='&copy; OpenStreetMap contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            <Circle
                center={position}
                radius={20}
                pathOptions={{
                    fillOpacity: 0.12,
                    weight: 2,
                }}
            />

            <Marker
                position={position}
                icon={droneIcon}
            >
                <Popup>
                    <div className="min-w-44">
                        <strong>{drone.name}</strong>

                        <p className="mt-1 font-mono text-xs">
                            {drone.droneCode}
                        </p>

                        <dl className="mt-3 space-y-1 text-xs">
                            <div>
                                <dt className="inline font-semibold">
                                    위도:
                                </dt>{" "}
                                <dd className="inline">
                                    {drone.latitude.toFixed(7)}
                                </dd>
                            </div>

                            <div>
                                <dt className="inline font-semibold">
                                    경도:
                                </dt>{" "}
                                <dd className="inline">
                                    {drone.longitude.toFixed(7)}
                                </dd>
                            </div>

                            <div>
                                <dt className="inline font-semibold">
                                    고도:
                                </dt>{" "}
                                <dd className="inline">
                                    {drone.altitude !== null
                                        ? `${drone.altitude.toFixed(2)} m`
                                        : "-"}
                                </dd>
                            </div>

                            <div>
                                <dt className="inline font-semibold">
                                    배터리:
                                </dt>{" "}
                                <dd className="inline">
                                    {drone.batteryLevel !== null
                                        ? `${drone.batteryLevel}%`
                                        : "-"}
                                </dd>
                            </div>
                        </dl>
                    </div>
                </Popup>
            </Marker>

            <MapPositionController
                latitude={drone.latitude}
                longitude={drone.longitude}
            />
        </MapContainer>
    );
}