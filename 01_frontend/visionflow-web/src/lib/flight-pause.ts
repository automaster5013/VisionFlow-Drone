export type FlightPause = { pausedAt: string; resumedAt: string | null };

export function pausedSecondsBetween(from: number, to: number, pauses: FlightPause[] = []): number {
  // Merge overlaps defensively; never infer a pause from missing telemetry.
  const intervals = pauses.flatMap(p => {
    if (!p.resumedAt) return [];
    const start = Math.max(from, Date.parse(p.pausedAt));
    const end = Math.min(to, Date.parse(p.resumedAt));
    return Number.isFinite(start) && Number.isFinite(end) && end > start ? [[start, end]] : [];
  }).sort((a, b) => a[0] - b[0]);
  let total = 0, lastEnd = from;
  for (const [start, end] of intervals) {
    total += Math.max(0, end - Math.max(start, lastEnd));
    lastEnd = Math.max(lastEnd, end);
  }
  return total / 1000;
}
