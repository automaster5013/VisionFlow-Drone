export interface OperatorManagedSession {
  sessionId: string;
  username: string;
  role: string;
  issuedAt: string;
  lastSeenAt: string;
  idleExpiresAt: string;
  expiresAt: string;
  clientFingerprint: string;
  current: boolean;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isSession(value: unknown): value is OperatorManagedSession {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.sessionId === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      value.sessionId,
    ) &&
    typeof value.username === "string" &&
    typeof value.role === "string" &&
    typeof value.issuedAt === "string" &&
    typeof value.lastSeenAt === "string" &&
    typeof value.idleExpiresAt === "string" &&
    typeof value.expiresAt === "string" &&
    typeof value.clientFingerprint === "string" &&
    typeof value.current === "boolean"
  );
}

export function parseOperatorSessions(
  value: unknown,
): OperatorManagedSession[] | null {
  return Array.isArray(value) && value.every(isSession) ? value : null;
}
