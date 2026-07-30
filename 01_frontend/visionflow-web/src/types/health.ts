export type ServiceStatus = "UP" | "DOWN" | "UNKNOWN";

export interface HealthData {
    service: string;
    applicationStatus: ServiceStatus;
    databaseStatus: ServiceStatus;
    checkedAt: string;
}

export interface ApiResponse<T> {
    success: boolean;
    data: T;
    timestamp: string;
}