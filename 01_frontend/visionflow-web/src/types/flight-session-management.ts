export type FlightSessionLifecycleStatus =
  | "READY"
  | "ACTIVE"
  | "COMPLETED"
  | "ABORTED";

export interface FlightSessionManagementResponse {
  sessionId: string;
  droneId: number;
  name: string;
  description: string | null;
  status: FlightSessionLifecycleStatus;
  sourceDeviceId: string | null;
  startedAt: string;
  endedAt: string | null;
  durationSeconds: number;
  createdAt: string;
  updatedAt: string;
}

export interface FlightSessionStartPayload {
  name?: string;
  description?: string;
  sourceDeviceId?: string;
}
