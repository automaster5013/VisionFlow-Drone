export function hasActivePresentation(payload: unknown, droneId: number): boolean {
  return Array.isArray(payload) && payload.some((entry: unknown) => {
    if (!entry || typeof entry !== "object") return false;
    const s = entry as Record<string, unknown>;
    return s.droneId === droneId && s.managed === true && s.status === "ACTIVE"
      && s.sourceDeviceId === "presentation-simulator-001";
  });
}

export function fleetFlightState(drone: { status: string; isStale: boolean }, presentation: boolean) {
  const simulated = presentation && !drone.isStale;
  const actual = !presentation && !drone.isStale && drone.status === "FLYING";
  return { simulated, actual, label: presentation
    ? (drone.isStale ? "시연 데이터 대기" : "시연 중")
    : (drone.isStale ? "STALE" : drone.status) };
}
