export interface DroneTelemetryHistory {
    id: number;
    droneId: number;
    latitude: number | null;
    longitude: number | null;
    altitude: number | null;
    batteryLevel: number | null;
    status: string;
    recordedAt: string;
}