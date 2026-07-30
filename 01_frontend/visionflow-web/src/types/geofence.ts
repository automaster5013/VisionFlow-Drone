export type GeofenceRule = "KEEP_IN" | "KEEP_OUT";

export type GeofenceEventState = "ACTIVE" | "RESOLVED";

export interface Geofence {
  id: number;
  name: string;
  ruleType: GeofenceRule;
  centerLatitude: number;
  centerLongitude: number;
  radiusMeters: number;
  active: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface GeofenceEvent {
  id: number;
  droneId: number;
  droneCode: string;
  geofenceId: number;
  geofenceName: string;
  ruleType: GeofenceRule;
  state: GeofenceEventState;
  latitude: number;
  longitude: number;
  altitude: number | null;
  distanceMeters: number;
  detectedAt: string;
  resolvedAt: string | null;
}

export interface GeofenceDraft {
  id: number | null;
  name: string;
  ruleType: GeofenceRule;
  centerLatitude: number | null;
  centerLongitude: number | null;
  radiusMeters: number;
}
