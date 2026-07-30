"use client";

import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import Link from "next/link";
import {
  Circle,
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";

import type { Geofence, GeofenceDraft } from "@/types/geofence";
import type { IncidentReplayFocus } from "@/types/incident-replay";
import type { MaintenanceFlightClearance } from "@/types/maintenance-flight-clearance";

import type {
  DroneTrackMap,
  DroneTrackPoint,
  FleetDrone,
} from "@/hooks/use-drone-fleet-telemetry";

interface DroneControlMapProps {
  drones: FleetDrone[];
  tracksByDroneId: DroneTrackMap;
  geofences: Geofence[];
  activeGeofenceIds: number[];
  geofenceDraft: GeofenceDraft | null;
  onPickGeofenceCenter: (latitude: number, longitude: number) => void;

  replayPoint: {
    droneId: number;
    point: DroneTrackPoint;
  } | null;

  incidentFocus: IncidentReplayFocus | null;
  flightClearanceByDroneId: ReadonlyMap<
    number,
    MaintenanceFlightClearance
  >;

  selectedDroneId: number | null;
  onSelectDrone: (droneId: number) => void;
}

interface LocatedDrone extends FleetDrone {
  latitude: number;
  longitude: number;
}

const DEFAULT_CENTER: [number, number] = [37.5665, 126.978];

const STATUS_COLORS: Record<string, string> = {
  OFFLINE: "#64748b",
  ONLINE: "#22c55e",
  FLYING: "#3b82f6",
  CHARGING: "#eab308",
  MAINTENANCE: "#f97316",
  ERROR: "#ef4444",
};

function geofenceColor(
  geofence: Geofence,
  hasActiveViolation: boolean,
): string {
  if (!geofence.active) {
    return "#64748b";
  }

  if (hasActiveViolation) {
    return "#dc2626";
  }

  return geofence.ruleType === "KEEP_OUT" ? "#ef4444" : "#2563eb";
}

function hasValidLocation(drone: FleetDrone): drone is LocatedDrone {
  return (
    drone.latitude !== null &&
    drone.longitude !== null &&
    Number.isFinite(Number(drone.latitude)) &&
    Number.isFinite(Number(drone.longitude))
  );
}

function flightClearanceLabel(
  clearance: MaintenanceFlightClearance | undefined,
): string {
  if (!clearance) {
    return "조회 정보 없음";
  }
  if (!clearance.flightAllowed) {
    return "비행 차단";
  }
  return clearance.attentionRequired ? "점검 주의" : "비행 가능";
}

function createDroneIcon(
  drone: FleetDrone,
  clearance: MaintenanceFlightClearance | undefined,
  selected: boolean,
  replaying: boolean,
): L.DivIcon {
  const flightBlocked =
    clearance !== undefined && !clearance.flightAllowed;
  const flightAttention =
    clearance?.attentionRequired === true && !flightBlocked;
  const statusColor = flightBlocked
    ? "#dc2626"
    : flightAttention
      ? "#f59e0b"
      : replaying
        ? "#f59e0b"
        : drone.isStale
      ? "#64748b"
      : (STATUS_COLORS[drone.status] ?? "#64748b");
  const symbol = flightBlocked || flightAttention ? "!" : "✈";

  const size = selected ? 46 : 38;

  return L.divIcon({
    className: "",
    html: `
            <div style="
                width:${size}px;
                height:${size}px;
                display:flex;
                align-items:center;
                justify-content:center;
                border-radius:50%;
                color:white;
                font-size:${selected ? 23 : 19}px;
                background:${statusColor};
                border:${selected ? 4 : 3}px solid white;
                box-shadow:0 3px 14px rgba(15,23,42,0.45);
                transition:all 150ms ease;
            ">
                ${symbol}
            </div>
        `,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -(size / 2)],
  });
}

function createIncidentIcon(): L.DivIcon {
  return L.divIcon({
    className: "",
    html: `
      <div style="
        width:42px;
        height:42px;
        display:flex;
        align-items:center;
        justify-content:center;
        border-radius:50% 50% 50% 0;
        color:white;
        font-size:20px;
        background:#7c3aed;
        border:4px solid white;
        box-shadow:0 4px 16px rgba(76,29,149,0.55);
        transform:rotate(-45deg);
      ">
        <span style="transform:rotate(45deg)">!</span>
      </div>
    `,
    iconSize: [42, 42],
    iconAnchor: [21, 42],
    popupAnchor: [0, -40],
  });
}

function MapViewport({
  drones,
  selectedDroneId,
  incidentFocus,
}: {
  drones: LocatedDrone[];
  selectedDroneId: number | null;
  incidentFocus: IncidentReplayFocus | null;
}) {
  const map = useMap();
  const previousFleetKeyRef = useRef("");

  const fleetKey = drones
    .map((drone) => drone.id)
    .sort((a, b) => a - b)
    .join(",");

  const selectedDrone = drones.find((drone) => drone.id === selectedDroneId);

  const selectedLatitude = selectedDrone?.latitude;
  const selectedLongitude = selectedDrone?.longitude;
  const incidentLatitude = incidentFocus?.latitude ?? undefined;
  const incidentLongitude = incidentFocus?.longitude ?? undefined;

  useEffect(() => {
    if (incidentLatitude !== undefined && incidentLongitude !== undefined) {
      map.flyTo(
        [incidentLatitude, incidentLongitude],
        Math.max(map.getZoom(), 16),
        { animate: true, duration: 0.6 },
      );
      return;
    }

    if (selectedLatitude !== undefined && selectedLongitude !== undefined) {
      map.flyTo(
        [selectedLatitude, selectedLongitude],
        Math.max(map.getZoom(), 15),
        {
          animate: true,
          duration: 0.6,
        },
      );

      return;
    }

    if (fleetKey === previousFleetKeyRef.current || drones.length === 0) {
      return;
    }

    previousFleetKeyRef.current = fleetKey;

    if (drones.length === 1) {
      map.setView([drones[0].latitude, drones[0].longitude], 15);
      return;
    }

    const bounds = L.latLngBounds(
      drones.map((drone) => [drone.latitude, drone.longitude]),
    );

    map.fitBounds(bounds, {
      padding: [50, 50],
      maxZoom: 16,
    });
  }, [
    drones,
    fleetKey,
    incidentLatitude,
    incidentLongitude,
    map,
    selectedLatitude,
    selectedLongitude,
  ]);

  return null;
}

function GeofenceCenterPicker({
  enabled,
  onPick,
}: {
  enabled: boolean;
  onPick: (latitude: number, longitude: number) => void;
}) {
  const map = useMapEvents({
    click: (event) => {
      if (!enabled) {
        return;
      }

      onPick(event.latlng.lat, event.latlng.lng);
    },
  });

  useEffect(() => {
    const container = map.getContainer();
    const previousCursor = container.style.cursor;

    container.style.cursor = enabled ? "crosshair" : previousCursor;

    return () => {
      container.style.cursor = previousCursor;
    };
  }, [enabled, map]);

  return null;
}

export default function DroneControlMap({
  drones,
  tracksByDroneId,
  geofences,
  activeGeofenceIds,
  geofenceDraft,
  onPickGeofenceCenter,
  replayPoint,
  incidentFocus,
  flightClearanceByDroneId,
  selectedDroneId,
  onSelectDrone,
}: DroneControlMapProps) {
  const activeGeofenceIdSet = useMemo(
    () => new Set(activeGeofenceIds),
    [activeGeofenceIds],
  );

  const locatedDrones = useMemo<LocatedDrone[]>(() => {
    return drones.flatMap((drone) => {
      if (replayPoint?.droneId === drone.id) {
        return [
          {
            ...drone,
            latitude: replayPoint.point.latitude,
            longitude: replayPoint.point.longitude,
            altitude: replayPoint.point.altitude,
          },
        ];
      }

      if (!hasValidLocation(drone)) {
        return [];
      }

      return [
        {
          ...drone,
          latitude: Number(drone.latitude),
          longitude: Number(drone.longitude),
        },
      ];
    });
  }, [drones, replayPoint]);

  return (
    <MapContainer
      center={DEFAULT_CENTER}
      zoom={13}
      scrollWheelZoom
      className="h-[680px] w-full rounded-2xl"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      <MapViewport
        drones={locatedDrones}
        selectedDroneId={selectedDroneId}
        incidentFocus={incidentFocus}
      />

      <GeofenceCenterPicker
        enabled={geofenceDraft !== null}
        onPick={onPickGeofenceCenter}
      />

      {geofenceDraft !== null &&
        geofenceDraft.centerLatitude !== null &&
        geofenceDraft.centerLongitude !== null &&
        Number.isFinite(geofenceDraft.centerLatitude) &&
        Number.isFinite(geofenceDraft.centerLongitude) &&
        Number.isFinite(geofenceDraft.radiusMeters) &&
        geofenceDraft.radiusMeters > 0 && (
          <Circle
            center={[
              geofenceDraft.centerLatitude,
              geofenceDraft.centerLongitude,
            ]}
            radius={geofenceDraft.radiusMeters}
            pathOptions={{
              color: "#f59e0b",
              fillColor: "#fbbf24",
              fillOpacity: 0.2,
              opacity: 1,
              weight: 3,
              dashArray: "8 6",
            }}
          >
            <Popup>
              <div className="min-w-40 space-y-1">
                <strong>{geofenceDraft.name || "편집 중인 지오펜스"}</strong>
                <div>반경: {Math.round(geofenceDraft.radiusMeters)}m</div>
                <div className="text-amber-700">저장 전 미리보기</div>
              </div>
            </Popup>
          </Circle>
        )}

      {geofences.map((geofence) => {
        const latitude = Number(geofence.centerLatitude);
        const longitude = Number(geofence.centerLongitude);
        const radiusMeters = Number(geofence.radiusMeters);

        if (
          !Number.isFinite(latitude) ||
          !Number.isFinite(longitude) ||
          !Number.isFinite(radiusMeters) ||
          radiusMeters <= 0
        ) {
          return null;
        }

        const hasActiveViolation = activeGeofenceIdSet.has(geofence.id);
        const color = geofenceColor(geofence, hasActiveViolation);

        return (
          <Circle
            key={geofence.id}
            center={[latitude, longitude]}
            radius={radiusMeters}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: hasActiveViolation
                ? 0.28
                : geofence.active
                  ? 0.13
                  : 0.06,
              opacity: geofence.active ? 0.9 : 0.55,
              weight: hasActiveViolation ? 4 : 2,
              dashArray: geofence.active ? undefined : "8 6",
            }}
          >
            <Popup>
              <div className="min-w-48 space-y-1">
                <strong>{geofence.name}</strong>
                <div>
                  규칙:{" "}
                  {geofence.ruleType === "KEEP_OUT" ? "진입 금지" : "이탈 금지"}
                </div>
                <div>반경: {Math.round(radiusMeters)}m</div>
                <div>
                  상태:{" "}
                  {!geofence.active
                    ? "비활성"
                    : hasActiveViolation
                      ? "침범 발생"
                      : "정상"}
                </div>
              </div>
            </Popup>
          </Circle>
        );
      })}

      {Object.entries(tracksByDroneId).map(([droneIdText, track]) => {
        if (track.length < 2) {
          return null;
        }

        const droneId = Number(droneIdText);
        const selected = droneId === selectedDroneId;

        const drone = drones.find((item) => item.id === droneId);

        const lineColor = selected
          ? "#2563eb"
          : drone?.isStale
            ? "#94a3b8"
            : "#22c55e";

        return (
          <Polyline
            key={droneId}
            positions={track.map(
              (point) => [point.latitude, point.longitude] as [number, number],
            )}
            pathOptions={{
              color: lineColor,
              weight: selected ? 5 : 3,
              opacity: selected ? 0.95 : 0.65,
            }}
          />
        );
      })}

      {incidentFocus !== null &&
        incidentFocus.latitude !== null &&
        incidentFocus.longitude !== null && (
          <Marker
            position={[incidentFocus.latitude, incidentFocus.longitude]}
            icon={createIncidentIcon()}
            zIndexOffset={1_000}
          >
            <Popup>
              <div className="min-w-48 space-y-1">
                <strong>Incident #{incidentFocus.incidentId}</strong>
                <div>
                  원본:{" "}
                  {{
                    AI_ALERT: "AI 경보",
                    GEOFENCE: "지오펜스",
                    FLIGHT_QUALITY: "기체 신뢰도",
                    FLIGHT_GATE: "비행 시작 차단",
                  }[incidentFocus.sourceType]}
                </div>
                <div>
                  발생: {new Date(incidentFocus.occurredAt).toLocaleString("ko-KR")}
                </div>
                <div>
                  고도: {incidentFocus.altitude === null ? "-" : `${incidentFocus.altitude}m`}
                </div>
              </div>
            </Popup>
          </Marker>
        )}

      {locatedDrones.map((drone) => (
        <Marker
          key={drone.id}
          position={[drone.latitude, drone.longitude]}
          icon={createDroneIcon(
            drone,
            flightClearanceByDroneId.get(drone.id),
            selectedDroneId === drone.id,
            replayPoint?.droneId === drone.id,
          )}
          eventHandlers={{
            click: () => onSelectDrone(drone.id),
          }}
        >
          <Popup>
            <div className="min-w-44">
              <strong>{drone.name}</strong>

              <div>코드: {drone.droneCode}</div>
              <div>상태: {drone.isStale ? "STALE" : drone.status}</div>
              <div>고도: {drone.altitude ?? 0}m</div>
              <div>배터리: {drone.batteryLevel ?? 0}%</div>
              <div>
                비행 허가:{" "}
                {flightClearanceLabel(
                  flightClearanceByDroneId.get(drone.id),
                )}
              </div>
              {flightClearanceByDroneId.get(drone.id) && (
                <div className="mt-1 max-w-60 text-xs text-slate-600">
                  {flightClearanceByDroneId.get(drone.id)?.reason}
                </div>
              )}
              {flightClearanceByDroneId.get(drone.id)?.workOrderId !==
                null &&
                flightClearanceByDroneId.get(drone.id)?.workOrderId !==
                  undefined && (
                  <Link
                    href={
                      `/maintenance?droneId=${drone.id}` +
                      `&workOrderId=${
                        flightClearanceByDroneId.get(drone.id)?.workOrderId
                      }`
                    }
                    className="mt-2 block rounded-md bg-cyan-700 px-3 py-2 text-center text-xs font-bold text-white"
                  >
                    점검 작업 열기
                  </Link>
                )}
            </div>
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
