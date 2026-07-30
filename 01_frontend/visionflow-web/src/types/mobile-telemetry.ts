export type DroneTelemetrySource =
  | "API"
  | "SIMULATOR"
  | "MOBILE_SENSOR"
  | "DJI_DEVICE";

export interface MobileSensorSnapshot {
  latitude: number | null;
  longitude: number | null;
  altitude: number | null;
  heading: number | null;
  pitch: number | null;
  roll: number | null;
  groundSpeed: number | null;
  horizontalAccuracy: number | null;
  verticalAccuracy: number | null;
  capturedAt: number | null;
}

export interface MobileTelemetryPayload {
  latitude: number;
  longitude: number;
  altitude?: number;
  batteryLevel: number;
  heading?: number;
  pitch?: number;
  roll?: number;
  groundSpeed?: number;
  horizontalAccuracy?: number;
  verticalAccuracy?: number;
  telemetrySource: "MOBILE_SENSOR";
  sourceDeviceId: string;
  flightSessionId?: string;
}
