export function telemetryReception(now: number, receivedAt: number | null): "WAITING" | "LIVE" | "STALE" {
    if (receivedAt === null || !Number.isFinite(receivedAt)) return "WAITING";
    const age = now - receivedAt;
    return age >= -5000 && age <= 15000 ? "LIVE" : "STALE";
}
