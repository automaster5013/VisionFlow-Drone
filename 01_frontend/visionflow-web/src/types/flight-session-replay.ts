import type { AiInferenceEvent } from "@/types/ai-inference-event";

export type FlightSessionSummaryStatus =
  | "READY"
  | "ACTIVE"
  | "COMPLETED"
  | "ABORTED"
  | "LEGACY";

export interface FlightSessionSummary {
  sessionId: string;
  droneId: number;
  name: string;
  description: string | null;
  status: FlightSessionSummaryStatus;
  sourceDeviceId: string | null;
  startedAt: string;
  endedAt: string;
  durationSeconds: number;
  telemetryCount: number;
  aiEventCount: number;
  detectionCount: number;
  hasTelemetry: boolean;
  hasAiEvents: boolean;
  managed: boolean;
}

export interface FlightReplayTelemetry {
  id: number;
  droneId: number;
  latitude: number | string | null;
  longitude: number | string | null;
  altitude: number | string | null;
  batteryLevel: number | null;
  heading: number | string | null;
  pitch: number | string | null;
  roll: number | string | null;
  groundSpeed: number | string | null;
  horizontalAccuracy: number | string | null;
  verticalAccuracy: number | string | null;
  telemetrySource: string;
  sourceDeviceId: string | null;
  flightSessionId: string | null;
  status: string;
  recordedAt: string;
}

export interface FlightSessionReplay {
  sessionId: string;
  droneId: number;
  startedAt: string;
  endedAt: string;
  durationSeconds: number;
  telemetryCount: number;
  aiEventCount: number;
  detectionCount: number;
  telemetry: FlightReplayTelemetry[];
  aiEvents: AiInferenceEvent[];
}
