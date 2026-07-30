"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  buildFlightQualitySummary,
  type FlightQualitySummary,
} from "@/lib/flight-quality-summary";
import type { DashboardFlightSessionItem } from "@/types/operations-dashboard";
import type {
  FlightReplayTelemetry,
  FlightSessionReplay,
} from "@/types/flight-session-replay";

interface FlightPerformanceTrendPanelProps {
  sessions: DashboardFlightSessionItem[];
}

interface TrendMetrics {
  distanceMeters: number;
  maxAltitude: number | null;
  averageInferenceMs: number | null;
  detectionsPerMinute: number;
}

interface TrendPoint {
  session: DashboardFlightSessionItem;
  replay: FlightSessionReplay;
  metrics: TrendMetrics;
  quality: FlightQualitySummary;
}

interface TrendState {
  requestKey: string;
  points: TrendPoint[];
  failedCount: number;
  errorMessage: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isReplayResponse(value: unknown): value is FlightSessionReplay {
  return (
    isRecord(value) &&
    typeof value.sessionId === "string" &&
    typeof value.droneId === "number" &&
    typeof value.startedAt === "string" &&
    typeof value.endedAt === "string" &&
    typeof value.durationSeconds === "number" &&
    typeof value.telemetryCount === "number" &&
    typeof value.aiEventCount === "number" &&
    typeof value.detectionCount === "number" &&
    Array.isArray(value.telemetry) &&
    Array.isArray(value.aiEvents)
  );
}

async function readErrorMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const payload: unknown = await response.json();

    return isRecord(payload) && typeof payload.message === "string"
      ? payload.message
      : fallback;
  } catch {
    return fallback;
  }
}

function sessionKey(session: DashboardFlightSessionItem): string {
  return `${session.droneId}|${session.sessionId}`;
}

function numericValue(value: number | string | null): number | null {
  if (value === null) {
    return null;
  }

  const parsed = Number(value);

  return Number.isFinite(parsed) ? parsed : null;
}

function coordinate(
  telemetry: FlightReplayTelemetry,
): { latitude: number; longitude: number } | null {
  const latitude = numericValue(telemetry.latitude);
  const longitude = numericValue(telemetry.longitude);

  return latitude === null || longitude === null
    ? null
    : { latitude, longitude };
}

function distanceMeters(
  first: { latitude: number; longitude: number },
  second: { latitude: number; longitude: number },
): number {
  const earthRadiusMeters = 6_371_000;
  const toRadians = (value: number) => (value * Math.PI) / 180;
  const latitudeDelta = toRadians(second.latitude - first.latitude);
  const longitudeDelta = toRadians(second.longitude - first.longitude);
  const firstLatitude = toRadians(first.latitude);
  const secondLatitude = toRadians(second.latitude);
  const haversine =
    Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(firstLatitude) *
      Math.cos(secondLatitude) *
      Math.sin(longitudeDelta / 2) ** 2;

  return (
    2 *
    earthRadiusMeters *
    Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine))
  );
}

function calculateMetrics(replay: FlightSessionReplay): TrendMetrics {
  const coordinates = replay.telemetry
    .map(coordinate)
    .filter(
      (
        value,
      ): value is { latitude: number; longitude: number } =>
        value !== null,
    );
  let totalDistance = 0;

  for (let index = 1; index < coordinates.length; index += 1) {
    totalDistance += distanceMeters(
      coordinates[index - 1],
      coordinates[index],
    );
  }

  const altitudes = replay.telemetry
    .map((point) => numericValue(point.altitude))
    .filter((value): value is number => value !== null);
  const inferenceTimes = replay.aiEvents
    .map((event) => Number(event.inferenceMs))
    .filter(Number.isFinite);

  return {
    distanceMeters: totalDistance,
    maxAltitude: altitudes.length > 0 ? Math.max(...altitudes) : null,
    averageInferenceMs:
      inferenceTimes.length > 0
        ? inferenceTimes.reduce((sum, value) => sum + value, 0) /
          inferenceTimes.length
        : null,
    detectionsPerMinute:
      replay.durationSeconds > 0
        ? replay.detectionCount / (replay.durationSeconds / 60)
        : 0,
  };
}

async function loadTrendPoint(
  session: DashboardFlightSessionItem,
  signal: AbortSignal,
): Promise<TrendPoint> {
  const response = await fetch(
    `/api/drones/${session.droneId}/flight-sessions/` +
      `${encodeURIComponent(session.sessionId)}/replay` +
      "?telemetryLimit=5000&eventLimit=1000",
    {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal,
    },
  );

  if (!response.ok) {
    throw new Error(
      await readErrorMessage(
        response,
        `${session.name} 리플레이 조회 실패: ${response.status}`,
      ),
    );
  }

  const payload: unknown = await response.json();

  if (
    !isReplayResponse(payload) ||
    payload.droneId !== session.droneId ||
    payload.sessionId !== session.sessionId
  ) {
    throw new Error(`${session.name} 리플레이 응답 형식이 올바르지 않습니다.`);
  }

  return {
    session,
    replay: payload,
    metrics: calculateMetrics(payload),
    quality: buildFlightQualitySummary(payload, session.status),
  };
}

function timestamp(value: string): number {
  const parsed = new Date(value).getTime();

  return Number.isNaN(parsed) ? 0 : parsed;
}

function formatShortDate(value: string): string {
  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? "-"
    : date.toLocaleDateString("ko-KR", {
        month: "numeric",
        day: "numeric",
      });
}

function formatDistance(value: number): string {
  return value >= 1_000
    ? `${(value / 1_000).toFixed(2)}km`
    : `${Math.round(value)}m`;
}

function formatDelta(
  current: number | null,
  previous: number | null,
  unit: string,
  digits = 1,
): string {
  if (current === null || previous === null) {
    return "이전 값 없음";
  }

  const delta = current - previous;
  const sign = delta > 0 ? "+" : "";

  return `이전 대비 ${sign}${delta.toFixed(digits)}${unit}`;
}

function comparisonHref(left: TrendPoint, right: TrendPoint): string {
  const params = new URLSearchParams({
    left: sessionKey(left.session),
    right: sessionKey(right.session),
  });

  return `/flight-comparison?${params.toString()}`;
}

function reportHref(point: TrendPoint): string {
  return (
    `/drones/${point.session.droneId}/flight-sessions/` +
    `${encodeURIComponent(point.session.sessionId)}/report`
  );
}

function qualityGradeLabel(quality: FlightQualitySummary): string {
  return {
    EXCELLENT: "매우 우수",
    GOOD: "양호",
    CAUTION: "주의",
    RISK: "위험",
  }[quality.grade];
}

export function FlightPerformanceTrendPanel({
  sessions,
}: FlightPerformanceTrendPanelProps) {
  const candidates = useMemo(
    () =>
      sessions
        .filter(
          (session) =>
            session.status === "COMPLETED" ||
            session.status === "ABORTED",
        )
        .slice(0, 6),
    [sessions],
  );
  const requestKey = useMemo(
    () => candidates.map(sessionKey).join(","),
    [candidates],
  );
  const [state, setState] = useState<TrendState>({
    requestKey: "",
    points: [],
    failedCount: 0,
    errorMessage: null,
  });

  useEffect(() => {
    if (candidates.length === 0) {
      return;
    }

    const abortController = new AbortController();

    Promise.allSettled(
      candidates.map((session) =>
        loadTrendPoint(session, abortController.signal),
      ),
    )
      .then((results) => {
        if (abortController.signal.aborted) {
          return;
        }

        const points = results
          .filter(
            (result): result is PromiseFulfilledResult<TrendPoint> =>
              result.status === "fulfilled",
          )
          .map((result) => result.value)
          .sort(
            (left, right) =>
              timestamp(left.replay.endedAt) -
              timestamp(right.replay.endedAt),
          );

        setState({
          requestKey,
          points,
          failedCount: results.length - points.length,
          errorMessage:
            points.length === 0
              ? "최근 비행 리플레이를 불러오지 못했습니다."
              : null,
        });
      })
      .catch((loadError: unknown) => {
        if (
          loadError instanceof DOMException &&
          loadError.name === "AbortError"
        ) {
          return;
        }

        setState({
          requestKey,
          points: [],
          failedCount: candidates.length,
          errorMessage:
            loadError instanceof Error
              ? loadError.message
              : "비행 성과 추세를 불러오지 못했습니다.",
        });
      });

    return () => abortController.abort();
  }, [candidates, requestKey]);

  const resolved = state.requestKey === requestKey;
  const points = resolved ? state.points : [];
  const latest = points.at(-1) ?? null;
  const previous = points.at(-2) ?? null;
  const riskPoints = [...points]
    .reverse()
    .filter(
      (point) =>
        point.quality.criticalCount > 0 ||
        point.quality.warningCount > 0,
    );

  return (
    <article className="rounded-2xl border border-cyan-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900">
            최근 비행 성과 추세
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            완료·중단된 최근 세션 최대 6개의 운항 및 AI 성능 변화입니다.
          </p>
        </div>
        {latest && previous && (
          <Link
            href={comparisonHref(previous, latest)}
            className="rounded-lg bg-cyan-800 px-3 py-2 text-sm font-bold text-white hover:bg-cyan-700"
          >
            최근 2회 상세 비교
          </Link>
        )}
      </div>

      {candidates.length < 2 ? (
        <TrendNotice>
          추세를 계산하려면 완료 또는 중단된 비행 세션이 두 개 이상
          필요합니다.
        </TrendNotice>
      ) : !resolved ? (
        <TrendNotice>최근 비행 리플레이와 AI 지표를 계산하고 있습니다.</TrendNotice>
      ) : state.errorMessage ? (
        <div
          role="alert"
          className="mt-4 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          {state.errorMessage}
        </div>
      ) : latest && previous ? (
        <>
          {state.failedCount > 0 && (
            <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
              일부 리플레이 {state.failedCount}개를 불러오지 못해 조회 가능한
              세션만 표시합니다.
            </div>
          )}

          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <TrendMetricCard
              label="최근 품질 점수"
              value={`${latest.quality.score}점`}
              delta={`${qualityGradeLabel(latest.quality)} · ${formatDelta(
                latest.quality.score,
                previous.quality.score,
                "점",
                0,
              )}`}
            />
            <TrendMetricCard
              label="최근 이동 거리"
              value={formatDistance(latest.metrics.distanceMeters)}
              delta={formatDelta(
                latest.metrics.distanceMeters,
                previous.metrics.distanceMeters,
                "m",
                0,
              )}
            />
            <TrendMetricCard
              label="최근 분당 탐지"
              value={`${latest.metrics.detectionsPerMinute.toFixed(1)}개`}
              delta={formatDelta(
                latest.metrics.detectionsPerMinute,
                previous.metrics.detectionsPerMinute,
                "개",
              )}
            />
            <TrendMetricCard
              label="최근 평균 추론"
              value={
                latest.metrics.averageInferenceMs === null
                  ? "-"
                  : `${latest.metrics.averageInferenceMs.toFixed(1)}ms`
              }
              delta={formatDelta(
                latest.metrics.averageInferenceMs,
                previous.metrics.averageInferenceMs,
                "ms",
              )}
            />
            <TrendMetricCard
              label="최근 최대 고도"
              value={
                latest.metrics.maxAltitude === null
                  ? "-"
                  : `${latest.metrics.maxAltitude.toFixed(1)}m`
              }
              delta={formatDelta(
                latest.metrics.maxAltitude,
                previous.metrics.maxAltitude,
                "m",
              )}
            />
          </div>

          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <TrendBars
              title="비행 품질 점수"
              points={points}
              value={(point) => point.quality.score}
              formatter={(value) => `${Math.round(value)}점`}
              barClassName="bg-emerald-600"
            />
            <TrendBars
              title="이동 거리"
              points={points}
              value={(point) => point.metrics.distanceMeters}
              formatter={formatDistance}
              barClassName="bg-cyan-600"
            />
            <TrendBars
              title="분당 탐지"
              points={points}
              value={(point) => point.metrics.detectionsPerMinute}
              formatter={(value) => `${value.toFixed(1)}개`}
              barClassName="bg-violet-600"
            />
            <TrendBars
              title="평균 추론 시간"
              points={points}
              value={(point) => point.metrics.averageInferenceMs ?? 0}
              formatter={(value) => `${value.toFixed(1)}ms`}
              barClassName="bg-amber-500"
            />
          </div>

          <div className="mt-5 rounded-xl border border-slate-200 p-4">
            <div>
              <h3 className="font-black text-slate-900">
                주의·위험 세션 큐
              </h3>
              <p className="mt-1 text-xs text-slate-500">
                최근 비행 중 운영자가 우선 확인할 품질 진단 결과입니다.
              </p>
            </div>

            {riskPoints.length > 0 ? (
              <div className="mt-4 grid gap-3 lg:grid-cols-2">
                {riskPoints.map((point) => (
                  <QualityRiskCard
                    key={sessionKey(point.session)}
                    point={point}
                  />
                ))}
              </div>
            ) : (
              <div className="mt-4 rounded-lg bg-emerald-50 p-4 text-sm font-bold text-emerald-800">
                최근 조회 세션에서 주의·위험 진단이 발견되지 않았습니다.
              </div>
            )}
          </div>
        </>
      ) : (
        <TrendNotice>
          조회 가능한 리플레이가 두 개 미만이어서 추세를 표시할 수 없습니다.
        </TrendNotice>
      )}
    </article>
  );
}

function TrendNotice({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
      {children}
    </div>
  );
}

function TrendMetricCard({
  label,
  value,
  delta,
}: {
  label: string;
  value: string;
  delta: string;
}) {
  return (
    <div className="rounded-xl bg-slate-50 p-4">
      <div className="text-xs font-bold text-slate-500">{label}</div>
      <div className="mt-2 text-2xl font-black text-slate-950">{value}</div>
      <div className="mt-1 text-xs text-cyan-800">{delta}</div>
    </div>
  );
}

function QualityRiskCard({ point }: { point: TrendPoint }) {
  const critical = point.quality.criticalCount > 0;
  const primaryRisk = point.quality.primaryRisk;

  return (
    <div
      className={
        critical
          ? "rounded-xl border border-rose-200 bg-rose-50 p-4"
          : "rounded-xl border border-amber-200 bg-amber-50 p-4"
      }
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="break-words font-black text-slate-950">
            {point.session.name}
          </div>
          <div className="mt-1 text-xs text-slate-600">
            Drone #{point.session.droneId} ·{" "}
            {formatShortDate(point.replay.endedAt)}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div
            className={
              critical
                ? "text-2xl font-black text-rose-700"
                : "text-2xl font-black text-amber-700"
            }
          >
            {point.quality.score}
          </div>
          <div className="text-[10px] font-bold text-slate-500">
            {qualityGradeLabel(point.quality)}
          </div>
        </div>
      </div>

      {primaryRisk && (
        <div className="mt-3 rounded-lg bg-white/70 p-3 text-xs">
          <div className="font-black text-slate-900">
            {primaryRisk.title}
          </div>
          <div className="mt-1 text-slate-600">{primaryRisk.detail}</div>
        </div>
      )}

      <div className="mt-3 flex items-center justify-between gap-3">
        <div className="text-[11px] font-bold text-slate-600">
          위험 {point.quality.criticalCount} · 주의{" "}
          {point.quality.warningCount}
        </div>
        <Link
          href={reportHref(point)}
          className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white"
        >
          진단 보고서
        </Link>
      </div>
    </div>
  );
}

function TrendBars({
  title,
  points,
  value,
  formatter,
  barClassName,
}: {
  title: string;
  points: TrendPoint[];
  value: (point: TrendPoint) => number;
  formatter: (value: number) => string;
  barClassName: string;
}) {
  const values = points.map(value);
  const maximum = Math.max(...values, 1);

  return (
    <div className="rounded-xl border border-slate-200 p-4">
      <h3 className="text-sm font-black text-slate-800">{title}</h3>
      <div className="mt-4 flex h-36 items-end gap-2">
        {points.map((point, index) => {
          const pointValue = values[index];
          const height = `${Math.max(4, (pointValue / maximum) * 100)}%`;

          return (
            <div
              key={sessionKey(point.session)}
              className="flex min-w-0 flex-1 flex-col items-center justify-end"
            >
              <span className="mb-1 text-[10px] font-bold text-slate-600">
                {formatter(pointValue)}
              </span>
              <div
                title={`${point.session.name}: ${formatter(pointValue)}`}
                className={`w-full max-w-10 rounded-t ${barClassName}`}
                style={{ height }}
              />
              <span className="mt-2 text-[10px] text-slate-500">
                {formatShortDate(point.replay.endedAt)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
