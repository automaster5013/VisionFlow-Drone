export interface PresentationOrigin { latitude: number; longitude: number }

/** Deterministic, video-clock-driven simulated flight; no hardware commands. */
export function presentationTelemetry(seconds: number, duration: number, origin: PresentationOrigin) {
  if (![seconds, duration, origin.latitude, origin.longitude].every(Number.isFinite) || duration <= 0 || Math.abs(origin.latitude) > 85 || Math.abs(origin.longitude) > 180) {
    throw new Error("시연 시간과 기준 좌표를 확인하세요.");
  }
  const progress = Math.max(0, Math.min(1, seconds / duration));
  const angle = progress * 2 * Math.PI;
  const radius = 35;
  const metersPerDegree = 111_320;
  const altitude = Math.min(1, progress / 0.12, (1 - progress) / 0.12) * 30;
  const longitude = origin.longitude + radius * Math.sin(angle) / (metersPerDegree * Math.cos(origin.latitude * Math.PI / 180));
  return {
    latitude: origin.latitude + radius * (Math.cos(angle) - 1) / metersPerDegree,
    longitude: ((longitude + 540) % 360) - 180,
    altitude: Math.max(0, altitude),
    groundSpeed: progress >= 1 ? 0 : 2 * Math.PI * radius / duration,
    heading: (90 + progress * 360) % 360,
    pitch: progress < 0.12 ? 8 : progress > 0.88 ? -8 : 0,
    roll: progress > 0 && progress < 1 ? 4 : 0,
    batteryLevel: Math.round(100 - progress * 15),
    telemetrySource: "SIMULATOR" as const,
  };
}
