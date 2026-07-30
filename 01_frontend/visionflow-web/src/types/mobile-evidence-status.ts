export type MobileEvidenceReportStatus =
    | "SMARTPHONE_E2E_PASS"
    | "SMARTPHONE_E2E_BLOCKED";

export type MobileEvidenceFreshness = "FRESH" | "STALE" | "UNKNOWN";

export type MobileEvidenceIntegrity =
    | "VERIFIED"
    | "FAILED"
    | "NOT_AVAILABLE";

export interface MobileEvidenceSummary {
    passed: number;
    blocked: number;
}

export interface MobileEvidenceDetails {
    droneId: number;
    sessionIdMasked: string;
    sessionStatus: string;
    startedAt: string;
    endedAt: string | null;
    durationSeconds: number;
    sourceDeviceIdRecorded: boolean;
    telemetryCount: number;
    mobileSensorCount: number;
    gpsValueCount: number;
    orientationValueCount: number;
    aiEventCount: number;
    detectionCount: number;
}

export interface AvailableMobileEvidenceStatus {
    available: true;
    status: MobileEvidenceReportStatus;
    integrity: "VERIFIED";
    freshness: Exclude<MobileEvidenceFreshness, "UNKNOWN">;
    generatedAt: string;
    ageHours: number;
    artifactName: string;
    checksumSha256: string;
    summary: MobileEvidenceSummary;
    evidence: MobileEvidenceDetails;
}

export interface UnavailableMobileEvidenceStatus {
    available: false;
    status: "SMARTPHONE_E2E_UNAVAILABLE" | "SMARTPHONE_E2E_INVALID";
    integrity: Exclude<MobileEvidenceIntegrity, "VERIFIED">;
    freshness: "UNKNOWN";
    generatedAt: null;
    message: string;
}

export type MobileEvidenceStatus =
    | AvailableMobileEvidenceStatus
    | UnavailableMobileEvidenceStatus;
