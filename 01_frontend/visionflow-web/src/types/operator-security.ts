export type OperatorAuthMode = "static" | "session";

export type OperatorRole =
  | "LOCAL"
  | "VIEWER"
  | "OPERATOR"
  | "ADMIN"
  | "INVALID_SESSION"
  | "INVALID_KEY";

export interface OperatorSecurityStatus {
  enabled: boolean;
  authenticated: boolean;
  username: string | null;
  role: OperatorRole | string | null;
}
