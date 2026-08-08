import { redirect } from "next/navigation";

import { DroneFleetControl } from "@/components/drones/drone-fleet-control";
import {
  getOperatorAuthMode,
  withBackendOperatorAuth,
} from "@/lib/server/operator-auth";
import type { Drone } from "@/types/drone";
import type { IncidentReplayFocus } from "@/types/incident-replay";
import {
  parseMaintenanceFleetFlightClearance,
  type MaintenanceFleetFlightClearance,
} from "@/types/maintenance-flight-clearance";

type SearchValue = string | string[] | undefined;

interface DronesPageProps {
  searchParams: Promise<Record<string, SearchValue>>;
}

function firstSearchValue(value: SearchValue): string {
  return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
}

function buildDronesReturnTo(query: Record<string, SearchValue>): string {
  const params = new URLSearchParams();

  for (const [key, value] of Object.entries(query)) {
    if (Array.isArray(value)) {
      for (const item of value) {
        params.append(key, item);
      }
    } else if (typeof value === "string") {
      params.set(key, value);
    }
  }

  const search = params.toString();
  return search ? `/drones?${search}` : "/drones";
}

function parseOptionalNumber(value: string): number | null {
  if (!value) {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function extractDrones(payload: unknown): Drone[] {
  // 백엔드가 배열을 직접 반환하는 경우
  if (Array.isArray(payload)) {
    return payload as Drone[];
  }

  if (payload && typeof payload === "object") {
    const response = payload as {
      data?: unknown;
      content?: unknown;
      items?: unknown;
    };

    // { data: [...] }
    if (Array.isArray(response.data)) {
      return response.data as Drone[];
    }

    // Spring Page 응답: { content: [...] }
    if (Array.isArray(response.content)) {
      return response.content as Drone[];
    }

    // { items: [...] }
    if (Array.isArray(response.items)) {
      return response.items as Drone[];
    }
  }

  throw new Error(
      `드론 목록 응답이 배열 형식이 아닙니다: ${JSON.stringify(payload)}`,
  );
}

async function getInitialFleetClearance(
  backendApiUrl: string,
): Promise<MaintenanceFleetFlightClearance | null> {
  try {
    const response = await fetch(
      `${backendApiUrl}/api/maintenance/flight-clearance`,
      await withBackendOperatorAuth({
        cache: "no-store",
        signal: AbortSignal.timeout(5_000),
      }),
    );
    if (!response.ok) {
      console.error(
        "GET /api/maintenance/flight-clearance 실패:",
        response.status,
        response.statusText,
      );
      return null;
    }

    const parsed = parseMaintenanceFleetFlightClearance(
      await response.json() as unknown,
    );
    if (!parsed) {
      console.error("함대 비행 허가 상태 응답 형식이 올바르지 않습니다.");
    }
    return parsed;
  } catch (error) {
    console.error("함대 비행 허가 상태 초기 조회 오류:", error);
    return null;
  }
}

export default async function DronesPage({ searchParams }: DronesPageProps) {
  const query = await searchParams;
  const rawDroneId = firstSearchValue(query.droneId);
  const rawSessionId = firstSearchValue(query.sessionId);
  const rawIncidentId = firstSearchValue(query.incidentId);
  const rawIncidentAt = firstSearchValue(query.incidentAt);
  const rawIncidentSource = firstSearchValue(query.incidentSource);
  const incidentLatitude = parseOptionalNumber(
    firstSearchValue(query.incidentLat),
  );
  const incidentLongitude = parseOptionalNumber(
    firstSearchValue(query.incidentLng),
  );
  const incidentAltitude = parseOptionalNumber(
    firstSearchValue(query.incidentAlt),
  );
  const requestedDroneId = /^\d+$/.test(rawDroneId)
    ? Number(rawDroneId)
    : null;
  const backendApiUrl = (
    process.env.BACKEND_API_URL ??
    process.env.SPRING_API_URL ??
    "http://localhost:8080"
  ).replace(/\/$/, "");
  const [response, initialFleetClearance] = await Promise.all([
    fetch(
      `${backendApiUrl}/api/drones`,
      await withBackendOperatorAuth({
        cache: "no-store",
      }),
    ),
    getInitialFleetClearance(backendApiUrl),
  ]);

  if (response.status === 401) {
    if (getOperatorAuthMode() === "session") {
      const returnTo = buildDronesReturnTo(query);
      redirect(`/operator-login?returnTo=${encodeURIComponent(returnTo)}`);
    }

    throw new Error(
      `드론 목록 조회 인증 실패: ${response.status} ${response.statusText}`,
    );
  }

  if (!response.ok) {
    throw new Error(
        `드론 목록 조회 실패: ${response.status} ${response.statusText}`,
    );
  }

  const drones = extractDrones(await response.json() as unknown);
  const initialSelectedDroneId =
    requestedDroneId !== null &&
    requestedDroneId > 0 &&
    drones.some((drone) => drone.id === requestedDroneId)
      ? requestedDroneId
      : null;
  const initialReplaySessionId =
    initialSelectedDroneId !== null &&
    rawSessionId.length >= 1 &&
    rawSessionId.length <= 36
      ? rawSessionId
      : null;
  const validIncidentSource =
    rawIncidentSource === "AI_ALERT" ||
    rawIncidentSource === "GEOFENCE" ||
    rawIncidentSource === "FLIGHT_QUALITY" ||
    rawIncidentSource === "FLIGHT_GATE"
      ? rawIncidentSource
      : null;
  const coordinatesValid =
    incidentLatitude !== null &&
    incidentLatitude >= -90 &&
    incidentLatitude <= 90 &&
    incidentLongitude !== null &&
    incidentLongitude >= -180 &&
    incidentLongitude <= 180;
  const initialIncidentFocus: IncidentReplayFocus | null =
    initialSelectedDroneId !== null &&
    /^\d+$/.test(rawIncidentId) &&
    Number(rawIncidentId) > 0 &&
    rawIncidentAt.length <= 40 &&
    Number.isFinite(Date.parse(rawIncidentAt)) &&
    validIncidentSource !== null
      ? {
          incidentId: Number(rawIncidentId),
          sourceType: validIncidentSource,
          occurredAt: rawIncidentAt,
          latitude: coordinatesValid ? incidentLatitude : null,
          longitude: coordinatesValid ? incidentLongitude : null,
          altitude: incidentAltitude,
        }
      : null;
  const controlKey = [
    initialSelectedDroneId ?? "none",
    initialReplaySessionId ?? "none",
    initialIncidentFocus?.incidentId ?? "none",
  ].join(":");

  return (
      <main className="p-6">
        <DroneFleetControl
          key={controlKey}
          initialDrones={drones}
          initialSelectedDroneId={initialSelectedDroneId}
          initialReplaySessionId={initialReplaySessionId}
          initialIncidentFocus={initialIncidentFocus}
          initialFleetClearance={initialFleetClearance}
        />
      </main>
  );
}
