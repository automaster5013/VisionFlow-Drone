export type MobileHttpsRuntimeState =
  | "READY"
  | "BLOCKED"
  | "STALE"
  | "UNAVAILABLE";

export interface MobileHttpsRuntimeCertificate {
  available: boolean;
  sanMatch: boolean;
  sanIps: string[];
  notAfter: string | null;
  expired: boolean;
}

export interface MobileHttpsRuntimeHealth {
  status: "PASS" | "BLOCKED" | "FAIL" | "UNKNOWN";
  url: string | null;
  httpStatus: number | null;
  error: string | null;
}

export interface MobileHttpsRuntimeProfile {
  available: boolean;
  state: MobileHttpsRuntimeState;
  ready: boolean;
  fresh: boolean;
  generatedAt: string | null;
  ageSeconds: number | null;
  hostIp: string | null;
  candidateIps: string[];
  origin: string | null;
  port: number;
  detectionSource: string | null;
  certificate: MobileHttpsRuntimeCertificate | null;
  https: MobileHttpsRuntimeHealth | null;
  message: string;
}
