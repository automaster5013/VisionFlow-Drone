"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Client, type IMessage } from "@stomp/stompjs";

import { resolveWebSocketUrl } from "@/lib/websocket-url";
import type { Drone } from "@/types/drone";
import type { WebSocketConnectionStatus } from "@/types/websocket";
import type { DroneTelemetryHistory } from "@/types/drone-telemetry-history";
import type { Geofence, GeofenceEvent } from "@/types/geofence";
import type { AiInferenceEvent } from "@/types/ai-inference-event";

const STALE_AFTER_MS = 15_000;
// const STALE_AFTER_MS = 5 * 60 * 1_000;
const CLOCK_INTERVAL_MS = 5_000;

const MAX_TRACK_POINTS = 200;
const HISTORY_LIMIT = MAX_TRACK_POINTS;
const DUPLICATE_TIME_WINDOW_MS = 10_000;
const MAX_AI_EVENTS = 100;

export interface DroneTrackPoint {
  latitude: number;
  longitude: number;
  altitude: number | null;
  heading?: number | null;
  receivedAt: number;
}

export type DroneTrackMap = Record<number, DroneTrackPoint[]>;

interface RealtimeDroneEntry {
  drone: Drone;
  receivedAt: number;
}

export interface FleetDrone extends Drone {
  isStale: boolean;
  realtimeReceivedAt: string | null;
}

interface UseDroneFleetTelemetryResult {
  drones: FleetDrone[];
  connectionStatus: WebSocketConnectionStatus;
  lastMessageAt: Date | null;
  tracksByDroneId: DroneTrackMap;
  geofences: Geofence[];
  geofenceEvents: GeofenceEvent[];
  geofenceLoadError: string | null;
  refreshGeofences: () => Promise<void>;
  aiEvents: AiInferenceEvent[];
  aiEventLoadError: string | null;
  refreshAiEvents: () => Promise<void>;
  clearTrack: (droneId?: number) => void;

  replaceTrack: (droneId: number, points: DroneTrackPoint[]) => void;
}

function upsertGeofenceEvent(
  current: GeofenceEvent[],
  incoming: GeofenceEvent,
): GeofenceEvent[] {
  const next = [
    incoming,
    ...current.filter((event) => event.id !== incoming.id),
  ];

  return next
    .sort(
      (first, second) =>
        parseRecordedAt(second.detectedAt) - parseRecordedAt(first.detectedAt),
    )
    .slice(0, 100);
}

function isGeofenceEvent(value: unknown): value is GeofenceEvent {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Partial<GeofenceEvent>;

  return (
    typeof candidate.id === "number" &&
    Number.isFinite(candidate.id) &&
    typeof candidate.droneId === "number" &&
    Number.isFinite(candidate.droneId) &&
    typeof candidate.geofenceId === "number" &&
    Number.isFinite(candidate.geofenceId) &&
    (candidate.state === "ACTIVE" || candidate.state === "RESOLVED")
  );
}

function isAiInferenceEvent(value: unknown): value is AiInferenceEvent {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Partial<AiInferenceEvent>;

  return (
    typeof candidate.id === "number" &&
    Number.isFinite(candidate.id) &&
    typeof candidate.droneId === "number" &&
    Number.isFinite(candidate.droneId) &&
    typeof candidate.frameIndex === "number" &&
    Number.isFinite(candidate.frameIndex) &&
    typeof candidate.capturedAt === "string" &&
    typeof candidate.receivedAt === "string" &&
    typeof candidate.detectionCount === "number" &&
    Array.isArray(candidate.detections)
  );
}

function upsertAiInferenceEvent(
  current: AiInferenceEvent[],
  incoming: AiInferenceEvent,
): AiInferenceEvent[] {
  return [incoming, ...current.filter((event) => event.id !== incoming.id)]
    .sort(
      (first, second) =>
        parseRecordedAt(second.receivedAt) - parseRecordedAt(first.receivedAt),
    )
    .slice(0, MAX_AI_EVENTS);
}

async function fetchAiInferenceEvents(
  signal?: AbortSignal,
): Promise<AiInferenceEvent[]> {
  const response = await fetch(`/api/ai/events?limit=${MAX_AI_EVENTS}`, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    cache: "no-store",
    signal,
  });

  if (!response.ok) {
    throw new Error(`AI 추론 이벤트 조회 실패: ${response.status}`);
  }

  const payload: unknown = await response.json();

  if (!Array.isArray(payload)) {
    throw new Error("AI 추론 이벤트 응답이 배열이 아닙니다.");
  }

  return payload.filter(isAiInferenceEvent);
}

function sameCoordinate(
  first: DroneTrackPoint,
  second: DroneTrackPoint,
): boolean {
  return (
    Math.abs(first.latitude - second.latitude) < 0.0000001 &&
    Math.abs(first.longitude - second.longitude) < 0.0000001
  );
}

function mergeTrackPoints(
  existing: DroneTrackPoint[],
  incoming: DroneTrackPoint[],
): DroneTrackPoint[] {
  const sorted = [...existing, ...incoming].sort(
    (first, second) => first.receivedAt - second.receivedAt,
  );

  const merged: DroneTrackPoint[] = [];

  for (const point of sorted) {
    const lastPoint = merged[merged.length - 1];

    const isDuplicate =
      lastPoint !== undefined &&
      sameCoordinate(lastPoint, point) &&
      Math.abs(lastPoint.receivedAt - point.receivedAt) <=
        DUPLICATE_TIME_WINDOW_MS;

    if (isDuplicate) {
      // 과거 API 좌표와 동일한 실시간 좌표가
      // 겹치면 더 최근 시각을 유지
      if (point.receivedAt >= lastPoint.receivedAt) {
        merged[merged.length - 1] = point;
      }

      continue;
    }

    merged.push(point);
  }

  return merged.slice(-MAX_TRACK_POINTS);
}

function parseRecordedAt(value: string): number {
  // Java LocalDateTime의 마이크로초 6자리를
  // JavaScript 밀리초 3자리로 변환
  const normalized = value.replace(/(\.\d{3})\d+(?=Z|[+-]\d{2}:\d{2}|$)/, "$1");

  return new Date(normalized).getTime();
}

function historyToTrackPoint(
  history: DroneTelemetryHistory,
): DroneTrackPoint | null {
  if (history.latitude === null || history.longitude === null) {
    return null;
  }

  const latitude = Number(history.latitude);
  const longitude = Number(history.longitude);

  const altitude = history.altitude === null ? null : Number(history.altitude);

  const historyWithHeading = history as DroneTelemetryHistory & {
    heading?: unknown;
  };
  const heading =
    historyWithHeading.heading === null ||
    historyWithHeading.heading === undefined
      ? null
      : Number(historyWithHeading.heading);

  const receivedAt = parseRecordedAt(history.recordedAt);

  if (
    !Number.isFinite(latitude) ||
    !Number.isFinite(longitude) ||
    !Number.isFinite(receivedAt)
  ) {
    return null;
  }

  return {
    latitude,
    longitude,
    altitude: altitude !== null && Number.isFinite(altitude) ? altitude : null,
    heading: heading !== null && Number.isFinite(heading) ? heading : null,
    receivedAt,
  };
}

export function useDroneFleetTelemetry(
  initialDrones: Drone[],
): UseDroneFleetTelemetryResult {
  const clientRef = useRef<Client | null>(null);

  const [connectionStatus, setConnectionStatus] =
    useState<WebSocketConnectionStatus>("CONNECTING");

  const [realtimeById, setRealtimeById] = useState<
    Record<number, RealtimeDroneEntry>
  >({});

  const [lastMessageAt, setLastMessageAt] = useState<Date | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const [tracksByDroneId, setTracksByDroneId] = useState<DroneTrackMap>({});

  const [geofences, setGeofences] = useState<Geofence[]>([]);

  const [geofenceEvents, setGeofenceEvents] = useState<GeofenceEvent[]>([]);

  const [geofenceLoadError, setGeofenceLoadError] = useState<string | null>(
    null,
  );

  const [aiEvents, setAiEvents] = useState<AiInferenceEvent[]>([]);

  const [aiEventLoadError, setAiEventLoadError] = useState<string | null>(null);

  const historyDroneIdsKey = useMemo(() => {
    if (!Array.isArray(initialDrones)) {
      return "";
    }

    return initialDrones
      .map((drone) => drone.id)
      .filter((id) => Number.isFinite(id))
      .sort((first, second) => first - second)
      .join(",");
  }, [initialDrones]);

  const clearTrack = useCallback((droneId?: number) => {
    setTracksByDroneId((current) => {
      if (droneId === undefined) {
        return {};
      }

      if (!(droneId in current)) {
        return current;
      }

      const next = { ...current };
      delete next[droneId];

      return next;
    });
  }, []);

  const replaceTrack = useCallback(
    (droneId: number, points: DroneTrackPoint[]) => {
      setTracksByDroneId((current) => ({
        ...current,
        [droneId]: mergeTrackPoints([], points),
      }));
    },
    [],
  );

  const refreshGeofences = useCallback(async () => {
    setGeofenceLoadError(null);

    try {
      const [geofenceResponse, eventResponse] = await Promise.all([
        fetch("/api/geofences", {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
          cache: "no-store",
        }),
        fetch("/api/geofences/events?activeOnly=false&limit=100", {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
          cache: "no-store",
        }),
      ]);

      if (!geofenceResponse.ok) {
        throw new Error("지오펜스 목록 조회 실패: " + geofenceResponse.status);
      }

      if (!eventResponse.ok) {
        throw new Error("지오펜스 이벤트 조회 실패: " + eventResponse.status);
      }

      const geofencePayload: unknown = await geofenceResponse.json();
      const eventPayload: unknown = await eventResponse.json();

      if (!Array.isArray(geofencePayload)) {
        throw new Error("지오펜스 목록 응답이 배열이 아닙니다.");
      }

      if (!Array.isArray(eventPayload)) {
        throw new Error("지오펜스 이벤트 응답이 배열이 아닙니다.");
      }

      setGeofences(geofencePayload as Geofence[]);
      setGeofenceEvents((current) => {
        let next = current;

        for (const event of eventPayload) {
          if (isGeofenceEvent(event)) {
            next = upsertGeofenceEvent(next, event);
          }
        }

        return next;
      });
    } catch (error) {
      console.error("지오펜스 관제 데이터 새로고침 실패:", error);

      const message =
        error instanceof Error
          ? error.message
          : "지오펜스 관제 데이터를 새로고침하지 못했습니다.";

      setGeofenceLoadError(message);
      throw error;
    }
  }, []);

  const refreshAiEvents = useCallback(async () => {
    setAiEventLoadError(null);

    try {
      const events = await fetchAiInferenceEvents();

      setAiEvents((current) => {
        let next = current;

        for (const event of events) {
          next = upsertAiInferenceEvent(next, event);
        }

        return next;
      });
    } catch (error) {
      console.error("AI 추론 이벤트 새로고침 실패:", error);

      const message =
        error instanceof Error
          ? error.message
          : "AI 추론 이벤트를 새로고침하지 못했습니다.";

      setAiEventLoadError(message);
      throw error;
    }
  }, []);

  useEffect(() => {
    const timerId = window.setInterval(() => {
      setNow(Date.now());
    }, CLOCK_INTERVAL_MS);

    return () => {
      window.clearInterval(timerId);
    };
  }, []);

  useEffect(() => {
    const abortController = new AbortController();

    async function loadAiEvents() {
      try {
        setAiEventLoadError(null);

        const events = await fetchAiInferenceEvents(abortController.signal);

        if (abortController.signal.aborted) {
          return;
        }

        setAiEvents((current) => {
          let next = current;

          for (const event of events) {
            next = upsertAiInferenceEvent(next, event);
          }

          return next;
        });
      } catch (error) {
        if (abortController.signal.aborted) {
          return;
        }

        console.error("AI 추론 이벤트 초기 조회 실패:", error);

        setAiEventLoadError(
          error instanceof Error
            ? error.message
            : "AI 추론 이벤트를 불러오지 못했습니다.",
        );
      }
    }

    void loadAiEvents();

    return () => {
      abortController.abort();
    };
  }, []);

  useEffect(() => {
    const abortController = new AbortController();

    async function loadGeofenceMonitoring() {
      try {
        setGeofenceLoadError(null);

        const [geofenceResponse, eventResponse] = await Promise.all([
          fetch("/api/geofences", {
            method: "GET",
            headers: {
              Accept: "application/json",
            },
            cache: "no-store",
            signal: abortController.signal,
          }),
          fetch("/api/geofences/events" + "?activeOnly=false&limit=100", {
            method: "GET",
            headers: {
              Accept: "application/json",
            },
            cache: "no-store",
            signal: abortController.signal,
          }),
        ]);

        if (!geofenceResponse.ok) {
          throw new Error(
            "지오펜스 목록 조회 실패: " + geofenceResponse.status,
          );
        }

        if (!eventResponse.ok) {
          throw new Error("지오펜스 이벤트 조회 실패: " + eventResponse.status);
        }

        const geofencePayload: unknown = await geofenceResponse.json();
        const eventPayload: unknown = await eventResponse.json();

        if (!Array.isArray(geofencePayload)) {
          throw new Error("지오펜스 목록 응답이 배열이 아닙니다.");
        }

        if (!Array.isArray(eventPayload)) {
          throw new Error("지오펜스 이벤트 응답이 배열이 아닙니다.");
        }

        if (abortController.signal.aborted) {
          return;
        }

        setGeofences(geofencePayload as Geofence[]);
        setGeofenceEvents((current) => {
          let next = current;

          for (const event of eventPayload) {
            if (isGeofenceEvent(event)) {
              next = upsertGeofenceEvent(next, event);
            }
          }

          return next;
        });
      } catch (error) {
        if (abortController.signal.aborted) {
          return;
        }

        console.error("지오펜스 관제 데이터 조회 실패:", error);

        setGeofenceLoadError(
          error instanceof Error
            ? error.message
            : "지오펜스 관제 데이터를 불러오지 못했습니다.",
        );
      }
    }

    void loadGeofenceMonitoring();

    return () => {
      abortController.abort();
    };
  }, []);

  useEffect(() => {
    if (!historyDroneIdsKey) {
      return;
    }

    const abortController = new AbortController();

    const droneIds = historyDroneIdsKey
      .split(",")
      .map(Number)
      .filter(Number.isFinite);

    async function loadHistory(droneId: number): Promise<{
      droneId: number;
      points: DroneTrackPoint[];
    }> {
      const response = await fetch(
        `/api/drones/${droneId}/telemetry/history` + `?limit=${HISTORY_LIMIT}`,
        {
          method: "GET",
          headers: {
            Accept: "application/json",
          },
          cache: "no-store",
          signal: abortController.signal,
        },
      );

      if (!response.ok) {
        throw new Error(
          `${droneId}번 드론 경로 조회 실패: ` + `${response.status}`,
        );
      }

      const payload: unknown = await response.json();

      if (!Array.isArray(payload)) {
        throw new Error(`${droneId}번 드론 경로 응답이 배열이 아닙니다.`);
      }

      const points = (payload as DroneTelemetryHistory[])
        .map(historyToTrackPoint)
        .filter((point): point is DroneTrackPoint => point !== null);

      return {
        droneId,
        points,
      };
    }

    async function loadAllHistories() {
      const results = await Promise.allSettled(droneIds.map(loadHistory));

      if (abortController.signal.aborted) {
        return;
      }

      setTracksByDroneId((current) => {
        const next = { ...current };

        for (const result of results) {
          if (result.status === "rejected") {
            console.error("과거 경로 조회 실패:", result.reason);

            continue;
          }

          const { droneId, points } = result.value;

          next[droneId] = mergeTrackPoints(current[droneId] ?? [], points);
        }

        return next;
      });
    }

    void loadAllHistories();

    return () => {
      abortController.abort();
    };
  }, [historyDroneIdsKey]);

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

        console.log(
          "[STOMP] 전체 드론 실시간 연결 성공: /topic/drones/telemetry",
        );

        setConnectionStatus("CONNECTED");

        client.subscribe("/topic/drones/telemetry", (message: IMessage) => {
          console.log("[STOMP] 전체 드론 메시지 수신:", message.body);

          try {
            const incomingDrone = JSON.parse(message.body) as Drone;

            if (
              typeof incomingDrone.id !== "number" ||
              !Number.isFinite(incomingDrone.id)
            ) {
              console.error("잘못된 드론 텔레메트리:", incomingDrone);
              return;
            }

            const receivedAt = Date.now();

            setRealtimeById((current) => ({
              ...current,
              [incomingDrone.id]: {
                drone: incomingDrone,
                receivedAt,
              },
            }));

            const latitude = Number(incomingDrone.latitude);
            const longitude = Number(incomingDrone.longitude);

            const altitude =
              incomingDrone.altitude === null ||
              incomingDrone.altitude === undefined
                ? null
                : Number(incomingDrone.altitude);

            const incomingWithHeading = incomingDrone as Drone & {
              heading?: unknown;
            };
            const heading =
              incomingWithHeading.heading === null ||
              incomingWithHeading.heading === undefined
                ? null
                : Number(incomingWithHeading.heading);

            if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
              const trackPoint: DroneTrackPoint = {
                latitude,
                longitude,
                altitude:
                  altitude !== null && Number.isFinite(altitude)
                    ? altitude
                    : null,
                heading:
                  heading !== null && Number.isFinite(heading) ? heading : null,
                receivedAt,
              };

              setTracksByDroneId((current) => {
                const previousTrack = current[incomingDrone.id] ?? [];

                const nextTrack = mergeTrackPoints(previousTrack, [trackPoint]);

                return {
                  ...current,
                  [incomingDrone.id]: nextTrack,
                };
              });
            }

            setLastMessageAt(new Date(receivedAt));
          } catch (error) {
            console.error("전체 드론 텔레메트리 파싱 실패:", error);
          }
        });

        client.subscribe("/topic/geofences/events", (message: IMessage) => {
          try {
            const incomingEvent: unknown = JSON.parse(message.body);

            if (!isGeofenceEvent(incomingEvent)) {
              console.error("잘못된 지오펜스 이벤트:", incomingEvent);
              return;
            }

            setGeofenceEvents((current) =>
              upsertGeofenceEvent(current, incomingEvent),
            );
          } catch (error) {
            console.error("지오펜스 이벤트 파싱 실패:", error);
          }
        });

        client.subscribe("/topic/ai/events", (message: IMessage) => {
          try {
            const incomingEvent: unknown = JSON.parse(message.body);

            if (!isAiInferenceEvent(incomingEvent)) {
              console.error("잘못된 AI 추론 이벤트:", incomingEvent);
              return;
            }

            setAiEvents((current) =>
              upsertAiInferenceEvent(current, incomingEvent),
            );
          } catch (error) {
            console.error("AI 추론 이벤트 파싱 실패:", error);
          }
        });
      },

      onStompError: (frame) => {
        if (!active) {
          return;
        }

        console.error("STOMP 오류:", frame);
        setConnectionStatus("ERROR");
      },

      onWebSocketError: (event) => {
        if (!active) {
          return;
        }

        console.warn("WebSocket 연결 대기:", event);
        setConnectionStatus("ERROR");
      },

      onWebSocketClose: () => {
        if (!active) {
          return;
        }

        setConnectionStatus("DISCONNECTED");
      },
    });

    clientRef.current = client;
    client.activate();

    return () => {
      active = false;
      clientRef.current = null;
      void client.deactivate();
    };
  }, []);

  const drones = useMemo<FleetDrone[]>(() => {
    const safeInitialDrones = Array.isArray(initialDrones) ? initialDrones : [];

    const mergedById = new Map<number, Drone>();

    safeInitialDrones.forEach((drone) => {
      mergedById.set(drone.id, drone);
    });

    Object.values(realtimeById).forEach(({ drone }) => {
      mergedById.set(drone.id, drone);
    });

    console.table(
      Array.from(mergedById.values()).map((drone) => ({
        id: drone.id,
        name: drone.name,
        status: drone.status,
        realtimeReceivedAt: realtimeById[drone.id]?.receivedAt ?? null,
      })),
    );

    return Array.from(mergedById.values())
      .map((drone) => {
        const realtimeEntry = realtimeById[drone.id];

        const lastConnectedTime = drone.lastConnectedAt
          ? new Date(drone.lastConnectedAt).getTime()
          : 0;

        const latestTime = realtimeEntry?.receivedAt ?? lastConnectedTime;

        const isStale =
          latestTime === 0 ||
          !Number.isFinite(latestTime) ||
          now - latestTime > STALE_AFTER_MS;

        return {
          ...drone,
          isStale,
          realtimeReceivedAt: realtimeEntry
            ? new Date(realtimeEntry.receivedAt).toISOString()
            : null,
        };
      })
      .sort((a, b) => a.droneCode.localeCompare(b.droneCode, "ko"));
  }, [initialDrones, now, realtimeById]);

  return {
    drones,
    connectionStatus,
    lastMessageAt,
    tracksByDroneId,
    geofences,
    geofenceEvents,
    geofenceLoadError,
    refreshGeofences,
    aiEvents,
    aiEventLoadError,
    refreshAiEvents,
    clearTrack,
    replaceTrack,
  };
}
