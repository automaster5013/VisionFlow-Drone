export const DRONE_STATUSES = [
    "OFFLINE",
    "ONLINE",
    "FLYING",
    "CHARGING",
    "MAINTENANCE",
    "ERROR",
] as const;

export type DroneStatus = (typeof DRONE_STATUSES)[number];

export interface Drone {
    id: number;
    droneCode: string;
    name: string;
    modelName: string | null;
    serialNumber: string | null;
    status: DroneStatus;
    rtspUrl: string | null;
    latitude: number | null;
    longitude: number | null;
    altitude: number | null;
    batteryLevel: number | null;
    lastConnectedAt: string | null;
    createdAt: string;
    updatedAt: string;
}

export interface DroneCreateRequest {
    droneCode: string;
    name: string;
    modelName?: string | null;
    serialNumber?: string | null;
    status?: DroneStatus;
    rtspUrl?: string | null;
    latitude?: number | null;
    longitude?: number | null;
    altitude?: number | null;
    batteryLevel?: number | null;
    lastConnectedAt?: string | null;
}

export interface DroneUpdateRequest {
    name: string;
    modelName?: string | null;
    serialNumber?: string | null;
    rtspUrl?: string | null;
}

export interface DroneStatusUpdateRequest {
    status: DroneStatus;
}

export interface ApiResponse<T> {
    success: boolean;
    data: T;
    timestamp: string;
}

export interface ApiErrorResponse {
    success: false;
    code: string;
    message: string;
    errors?: Record<string, string>;
    timestamp: string;
}

export interface DeleteResponse {
    id: number;
    message: string;
}

export interface DroneTelemetryUpdateRequest {
    latitude?: number | null;
    longitude?: number | null;
    altitude?: number | null;
    batteryLevel?: number | null;
    lastConnectedAt?: string | null;
}