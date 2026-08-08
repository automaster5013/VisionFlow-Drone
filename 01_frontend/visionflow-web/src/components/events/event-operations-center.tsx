"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { EventDetailDrawer } from "@/components/events/event-detail-drawer";
import { formatKoreanDateTime } from "@/lib/date";
import { readOperatorConsolePreferences } from "@/lib/operator-console-settings";
import { parseAiAlertList } from "@/types/ai-alert";
import {
  buildEventOperationsTimeline,
  parseEventOperationsAiEvents,
  parseEventOperationsDrones,
  parseEventOperationsGeofenceEvents,
  type EventOperationsItem,
  type EventOperationsLifecycle,
  type EventOperationsSeverity,
  type EventOperationsSource,
  type EventOperationsSources,
} from "@/types/event-operations";
import { parseIncidentList } from "@/types/incident";
import type { EventTimeRange } from "@/types/operator-console-settings";

const AUTO_REFRESH_INTERVAL_MS = 15_000;
const DISPLAY_LIMIT = 100;

type SourceFilter = "" | EventOperationsSource;
type SeverityFilter = "" | EventOperationsSeverity;
type LifecycleFilter = "" | EventOperationsLifecycle;
type TimeRangeFilter = EventTimeRange;
type SourceHealthKey = "aiEvents" | "aiAlerts" | "geofenceEvents" | "incidents";

const EMPTY_SOURCES: EventOperationsSources = {
  drones: [],
  aiEvents: [],
  aiAlerts: [],
  geofenceEvents: [],
  incidents: [],
};

const SOURCE_PRESENTATION: Record<
  EventOperationsSource,
  { label: string; shortLabel: string; badge: string; marker: string }
> = {
  AI_ALERT: {
    label: "AI 경보",
    shortLabel: "AL",
    badge: "bg-rose-100 text-rose-800",
    marker: "border-rose-200 bg-rose-50 text-rose-700",
  },
  AI_INFERENCE: {
    label: "AI 추론",
    shortLabel: "AI",
    badge: "bg-violet-100 text-violet-800",
    marker: "border-violet-200 bg-violet-50 text-violet-700",
  },
  GEOFENCE: {
    label: "지오펜스",
    shortLabel: "GF",
    badge: "bg-amber-100 text-amber-900",
    marker: "border-amber-200 bg-amber-50 text-amber-700",
  },
  INCIDENT: {
    label: "Incident",
    shortLabel: "IN",
    badge: "bg-cyan-100 text-cyan-900",
    marker: "border-cyan-200 bg-cyan-50 text-cyan-700",
  },
};

const SEVERITY_PRESENTATION: Record<
  EventOperationsSeverity,
  { label: string; className: string }
> = {
  INFO: { label: "정보", className: "bg-sky-100 text-sky-800" },
  WARNING: { label: "주의", className: "bg-amber-100 text-amber-900" },
  CRITICAL: { label: "긴급", className: "bg-rose-100 text-rose-900" },
};

const SOURCE_HEALTH_LABELS: Record<SourceHealthKey, string> = {
  aiEvents: "AI 추론",
  aiAlerts: "AI 경보",
  geofenceEvents: "지오펜스",
  incidents: "Incident",
};

function errorMessage(body: unknown, fallback: string): string {
  if (
    typeof body === "object" &&
    body !== null &&
    "message" in body &&
    typeof body.message === "string"
  ) {
    return body.message;
  }
  return fallback;
}

async function fetchJson(url: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
    signal,
  });
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // JSON 본문이 없으면 HTTP 상태를 오류에 사용합니다.
  }

  if (!response.ok) {
    throw new Error(errorMessage(body, `HTTP ${response.status}`));
  }
  return body;
}

function resultError(result: PromiseSettledResult<unknown>, fallback: string): string {
  if (result.status === "rejected") {
    return result.reason instanceof Error ? result.reason.message : fallback;
  }
  return fallback;
}

function millisecondsForRange(range: TimeRangeFilter): number | null {
  return {
    "1H": 60 * 60 * 1_000,
    "6H": 6 * 60 * 60 * 1_000,
    "24H": 24 * 60 * 60 * 1_000,
    "7D": 7 * 24 * 60 * 60 * 1_000,
    ALL: null,
  }[range];
}

function relativeTime(value: string, nowMs: number): string {
  const occurredAt = Date.parse(value);
  if (!Number.isFinite(occurredAt)) return "시각 확인 필요";

  const seconds = Math.max(0, Math.floor((nowMs - occurredAt) / 1_000));
  if (seconds < 60) return `${seconds}초 전`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}분 전`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  return `${Math.floor(hours / 24)}일 전`;
}

function matchesSearch(event: EventOperationsItem, query: string): boolean {
  if (!query) return true;
  const normalized = query.toLocaleLowerCase("ko-KR");
  return [
    event.title,
    event.summary,
    event.droneLabel,
    event.statusLabel,
    String(event.sourceId),
  ].some((value) => value.toLocaleLowerCase("ko-KR").includes(normalized));
}

export function EventOperationsCenter() {
  const [consolePreferences] = useState(() => readOperatorConsolePreferences());
  const [sources, setSources] = useState<EventOperationsSources>(EMPTY_SOURCES);
  const [sourceErrors, setSourceErrors] = useState<Partial<Record<SourceHealthKey, string>>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(
    consolePreferences.eventAutoRefresh,
  );
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);
  const [clockMs, setClockMs] = useState(0);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("");
  const [droneFilter, setDroneFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("");
  const [lifecycleFilter, setLifecycleFilter] = useState<LifecycleFilter>("");
  const [timeRange, setTimeRange] = useState<TimeRangeFilter>(
    consolePreferences.eventTimeRange,
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedEvent, setSelectedEvent] = useState<EventOperationsItem | null>(null);
  const [returnFocusElement, setReturnFocusElement] = useState<HTMLButtonElement | null>(null);
  const requestSequence = useRef(0);
  const abortController = useRef<AbortController | null>(null);

  const refresh = useCallback(async (silent = false) => {
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    abortController.current?.abort();
    const controller = new AbortController();
    abortController.current = controller;

    if (!silent) setRefreshing(true);

    const [droneResult, aiEventResult, aiAlertResult, geofenceResult, incidentResult] =
      await Promise.allSettled([
        fetchJson("/api/drones", controller.signal),
        fetchJson("/api/ai/events?limit=100", controller.signal),
        fetchJson("/api/ai/alerts?limit=200", controller.signal),
        fetchJson("/api/geofences/events?activeOnly=false&limit=100", controller.signal),
        fetchJson("/api/incidents?limit=200", controller.signal),
      ]);

    if (controller.signal.aborted || sequence !== requestSequence.current) return;

    const nextErrors: Partial<Record<SourceHealthKey, string>> = {};
    const parsedDrones =
      droneResult.status === "fulfilled"
        ? parseEventOperationsDrones(droneResult.value)
        : null;
    const parsedAiEvents =
      aiEventResult.status === "fulfilled"
        ? parseEventOperationsAiEvents(aiEventResult.value)
        : null;
    const parsedAiAlerts =
      aiAlertResult.status === "fulfilled"
        ? parseAiAlertList(aiAlertResult.value)
        : null;
    const parsedGeofenceEvents =
      geofenceResult.status === "fulfilled"
        ? parseEventOperationsGeofenceEvents(geofenceResult.value)
        : null;
    const parsedIncidents =
      incidentResult.status === "fulfilled"
        ? parseIncidentList(incidentResult.value)
        : null;

    if (!parsedAiEvents) {
      nextErrors.aiEvents =
        aiEventResult.status === "fulfilled"
          ? "AI 추론 이벤트 응답 형식이 올바르지 않습니다."
          : resultError(aiEventResult, "AI 추론 이벤트를 조회하지 못했습니다.");
    }
    if (!parsedAiAlerts) {
      nextErrors.aiAlerts =
        aiAlertResult.status === "fulfilled"
          ? "AI 경보 응답 형식이 올바르지 않습니다."
          : resultError(aiAlertResult, "AI 경보를 조회하지 못했습니다.");
    }
    if (!parsedGeofenceEvents) {
      nextErrors.geofenceEvents =
        geofenceResult.status === "fulfilled"
          ? "지오펜스 이벤트 응답 형식이 올바르지 않습니다."
          : resultError(geofenceResult, "지오펜스 이벤트를 조회하지 못했습니다.");
    }
    if (!parsedIncidents) {
      nextErrors.incidents =
        incidentResult.status === "fulfilled"
          ? "Incident 응답 형식이 올바르지 않습니다."
          : resultError(incidentResult, "Incident를 조회하지 못했습니다.");
    }

    setSources((current) => ({
      drones: parsedDrones ?? current.drones,
      aiEvents: parsedAiEvents ?? current.aiEvents,
      aiAlerts: parsedAiAlerts ?? current.aiAlerts,
      geofenceEvents: parsedGeofenceEvents ?? current.geofenceEvents,
      incidents: parsedIncidents ?? current.incidents,
    }));

    setSourceErrors(nextErrors);
    const successfulSourceCount = [
      parsedAiEvents,
      parsedAiAlerts,
      parsedGeofenceEvents,
      parsedIncidents,
    ].filter((value) => value !== null).length;
    if (successfulSourceCount > 0) {
      const synchronizedAt = new Date();
      setLastUpdatedAt(synchronizedAt);
      setClockMs(synchronizedAt.getTime());
    }
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void refresh(), 0);
    return () => {
      window.clearTimeout(timeoutId);
      abortController.current?.abort();
    };
  }, [refresh]);

  useEffect(() => {
    if (!autoRefresh) return;

    const intervalId = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh(true);
    }, AUTO_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [autoRefresh, refresh]);

  useEffect(() => {
    const intervalId = window.setInterval(() => setClockMs(Date.now()), 30_000);
    return () => window.clearInterval(intervalId);
  }, []);

  const timeline = useMemo(() => buildEventOperationsTimeline(sources), [sources]);
  const nowMs = clockMs;
  const filteredEvents = useMemo(() => {
    const rangeMs = millisecondsForRange(timeRange);
    const sinceMs = rangeMs === null || nowMs === 0 ? null : nowMs - rangeMs;
    const normalizedQuery = searchQuery.trim();

    return timeline.filter((event) => {
      if (sourceFilter && event.source !== sourceFilter) return false;
      if (droneFilter && event.droneId !== Number(droneFilter)) return false;
      if (severityFilter && event.severity !== severityFilter) return false;
      if (lifecycleFilter && event.lifecycle !== lifecycleFilter) return false;
      if (sinceMs !== null) {
        const occurredAt = Date.parse(event.occurredAt);
        if (!Number.isFinite(occurredAt) || occurredAt < sinceMs) return false;
      }
      return matchesSearch(event, normalizedQuery);
    });
  }, [
    droneFilter,
    lifecycleFilter,
    nowMs,
    searchQuery,
    severityFilter,
    sourceFilter,
    timeRange,
    timeline,
  ]);

  const kpis = useMemo(() => {
    const oneHourAgo = nowMs - 60 * 60 * 1_000;
    return {
      openAlerts: sources.aiAlerts.filter((alert) => alert.status === "OPEN").length,
      activeIncidents: sources.incidents.filter(
        (incident) => incident.status === "OPEN" || incident.status === "IN_PROGRESS",
      ).length,
      activeGeofences: sources.geofenceEvents.filter((event) => event.state === "ACTIVE").length,
      recentInference: sources.aiEvents.filter((event) => Date.parse(event.capturedAt) >= oneHourAgo).length,
    };
  }, [nowMs, sources]);

  const sourceErrorCount = Object.keys(sourceErrors).length;
  const displayedEvents = filteredEvents.slice(0, DISPLAY_LIMIT);

  const resetFilters = () => {
    setSourceFilter("");
    setDroneFilter("");
    setSeverityFilter("");
    setLifecycleFilter("");
    setTimeRange("24H");
    setSearchQuery("");
  };

  const openDetail = (event: EventOperationsItem, button: HTMLButtonElement) => {
    setReturnFocusElement(button);
    setSelectedEvent(event);
  };

  const closeDetail = useCallback(() => setSelectedEvent(null), []);

  return (
    <div data-event-operations-center className="mx-auto max-w-[1500px] space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-black uppercase tracking-[0.18em] text-cyan-700">
            Event Operations Center
          </p>
          <h1 className="mt-1 text-3xl font-black text-slate-950 sm:text-4xl">
            통합 이벤트 관제 센터
          </h1>
          <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">
            AI 추론·경보, 지오펜스 위반과 Incident를 시간순으로 통합해
            기체별 운영 상황과 후속 조치 경로를 한 화면에서 확인합니다.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-bold text-slate-600">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(event) => setAutoRefresh(event.target.checked)}
              className="h-4 w-4 accent-cyan-600"
            />
            15초 자동 갱신
          </label>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={refreshing}
            className="rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-black text-white transition hover:bg-slate-800 disabled:cursor-wait disabled:opacity-60"
          >
            {refreshing ? "갱신 중" : "지금 갱신"}
          </button>
        </div>
      </header>

      <section className="overflow-hidden rounded-3xl bg-[linear-gradient(135deg,#031b2a_0%,#050b1d_55%,#17123b_100%)] p-5 text-white shadow-xl shadow-slate-300/40 sm:p-7">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.18em] text-cyan-300">
              Live Operations Summary
            </p>
            <h2 className="mt-1 text-2xl font-black">현재 대응 현황</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
            <span className={`rounded-full border px-3 py-1.5 ${
              sourceErrorCount === 0
                ? "border-emerald-300/40 bg-emerald-400/15 text-emerald-100"
                : "border-amber-300/40 bg-amber-400/15 text-amber-100"
            }`}>
              {sourceErrorCount === 0 ? "4개 소스 정상" : `${4 - sourceErrorCount}/4 소스 수신`}
            </span>
            <span className="rounded-full border border-slate-600 bg-slate-900/60 px-3 py-1.5 text-slate-300">
              {lastUpdatedAt
                ? `${formatKoreanDateTime(lastUpdatedAt.toISOString())} 갱신`
                : "초기 동기화 중"}
            </span>
          </div>
        </div>

        <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <SummaryCard label="미확인 AI 경보" value={kpis.openAlerts} unit="건" tone="rose" />
          <SummaryCard label="대응 중 Incident" value={kpis.activeIncidents} unit="건" tone="cyan" />
          <SummaryCard label="활성 지오펜스" value={kpis.activeGeofences} unit="건" tone="amber" />
          <SummaryCard label="최근 1시간 AI 추론" value={kpis.recentInference} unit="건" tone="violet" />
        </div>

        <div className="mt-5 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {(Object.keys(SOURCE_HEALTH_LABELS) as SourceHealthKey[]).map((key) => (
            <div
              key={key}
              className="flex items-center justify-between gap-3 rounded-xl border border-slate-700 bg-slate-950/40 px-3 py-2.5"
            >
              <span className="text-xs font-bold text-slate-300">{SOURCE_HEALTH_LABELS[key]}</span>
              <span className={`text-xs font-black ${sourceErrors[key] ? "text-amber-300" : "text-emerald-300"}`}>
                {sourceErrors[key] ? "부분 장애" : "정상"}
              </span>
            </div>
          ))}
        </div>
      </section>

      {sourceErrorCount > 0 && (
        <section className="rounded-2xl border border-amber-300 bg-amber-50 p-4" aria-live="polite">
          <h2 className="text-sm font-black text-amber-950">일부 이벤트 소스를 갱신하지 못했습니다.</h2>
          <ul className="mt-2 space-y-1 text-sm text-amber-900">
            {(Object.entries(sourceErrors) as Array<[SourceHealthKey, string]>).map(([key, message]) => (
              <li key={key}>• {SOURCE_HEALTH_LABELS[key]}: {message}</li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-amber-800">정상 수신된 소스와 마지막 유효 데이터는 계속 표시됩니다.</p>
        </section>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-black text-slate-950">관제 필터</h2>
            <p className="mt-1 text-sm text-slate-500">소스·기체·위험도·대응 상태와 시간 범위를 함께 적용합니다.</p>
          </div>
          <button
            type="button"
            onClick={resetFilters}
            className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-black text-slate-600 transition hover:border-slate-500"
          >
            필터 초기화
          </button>
        </div>

        <div data-event-operations-filters className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-6">
          <FilterSelect label="이벤트 소스" value={sourceFilter} onChange={(value) => setSourceFilter(value as SourceFilter)}>
            <option value="">전체 소스</option>
            <option value="AI_ALERT">AI 경보</option>
            <option value="AI_INFERENCE">AI 추론</option>
            <option value="GEOFENCE">지오펜스</option>
            <option value="INCIDENT">Incident</option>
          </FilterSelect>

          <FilterSelect label="기체" value={droneFilter} onChange={setDroneFilter}>
            <option value="">전체 기체</option>
            {sources.drones.map((drone) => (
              <option key={drone.id} value={String(drone.id)}>{drone.name} · {drone.droneCode}</option>
            ))}
          </FilterSelect>

          <FilterSelect label="위험도" value={severityFilter} onChange={(value) => setSeverityFilter(value as SeverityFilter)}>
            <option value="">전체 위험도</option>
            <option value="CRITICAL">긴급</option>
            <option value="WARNING">주의</option>
            <option value="INFO">정보</option>
          </FilterSelect>

          <FilterSelect label="대응 상태" value={lifecycleFilter} onChange={(value) => setLifecycleFilter(value as LifecycleFilter)}>
            <option value="">전체 상태</option>
            <option value="NEEDS_ACTION">조치 필요</option>
            <option value="MONITORING">확인·대응 중</option>
            <option value="COMPLETED">해결·기록 완료</option>
          </FilterSelect>

          <FilterSelect label="시간 범위" value={timeRange} onChange={(value) => setTimeRange(value as TimeRangeFilter)}>
            <option value="1H">최근 1시간</option>
            <option value="6H">최근 6시간</option>
            <option value="24H">최근 24시간</option>
            <option value="7D">최근 7일</option>
            <option value="ALL">전체 기간</option>
          </FilterSelect>

          <label className="block">
            <span className="text-xs font-black text-slate-500">검색</span>
            <input
              type="search"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="제목·기체·ID"
              className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none transition focus:border-cyan-600 focus:ring-2 focus:ring-cyan-100"
            />
          </label>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.16em] text-violet-700">Unified Event Timeline</p>
            <h2 className="mt-1 text-2xl font-black text-slate-950">통합 이벤트 타임라인</h2>
            <p className="mt-1 text-sm text-slate-500">발생 시각 기준 최신 순 · 최대 {DISPLAY_LIMIT}건 표시</p>
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1.5 text-sm font-black text-slate-700">
            조회 {filteredEvents.length}건
          </span>
        </div>

        {loading ? (
          <div className="mt-6 grid gap-3" aria-live="polite" aria-busy="true">
            {[0, 1, 2].map((index) => (
              <div key={index} className="h-32 animate-pulse rounded-2xl bg-slate-100" />
            ))}
          </div>
        ) : displayedEvents.length === 0 ? (
          <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-6 py-12 text-center">
            <p className="font-black text-slate-800">조건에 맞는 이벤트가 없습니다.</p>
            <p className="mt-2 text-sm text-slate-500">필터를 초기화하거나 조회 범위를 넓혀보세요.</p>
          </div>
        ) : (
          <ol data-event-operations-timeline className="mt-6 space-y-3">
            {displayedEvents.map((event, index) => {
              const source = SOURCE_PRESENTATION[event.source];
              const severity = SEVERITY_PRESENTATION[event.severity];
              return (
                <li key={event.key} className="relative pl-12 sm:pl-14">
                  {index < displayedEvents.length - 1 && (
                    <span aria-hidden="true" className="absolute left-[1.18rem] top-11 h-[calc(100%+0.75rem)] w-px bg-slate-200 sm:left-[1.42rem]" />
                  )}
                  <span
                    aria-hidden="true"
                    className={`absolute left-0 top-3 grid h-10 w-10 place-items-center rounded-xl border text-xs font-black sm:h-12 sm:w-12 ${source.marker}`}
                  >
                    {source.shortLabel}
                  </span>

                  <article className="rounded-2xl border border-slate-200 bg-white p-4 transition hover:border-cyan-300 hover:shadow-md sm:p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`rounded-full px-2.5 py-1 text-[11px] font-black ${source.badge}`}>{source.label}</span>
                          <span className={`rounded-full px-2.5 py-1 text-[11px] font-black ${severity.className}`}>{severity.label}</span>
                          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-black text-slate-600">{event.statusLabel}</span>
                        </div>
                        <h3 className="mt-3 text-base font-black text-slate-950 sm:text-lg">{event.title}</h3>
                        <p className="mt-1 line-clamp-2 text-sm leading-6 text-slate-600">{event.summary}</p>
                      </div>
                      <button
                        type="button"
                        onClick={(clickEvent) => openDetail(event, clickEvent.currentTarget)}
                        className="shrink-0 rounded-xl border border-slate-300 px-3 py-2 text-xs font-black text-slate-700 transition hover:border-cyan-500 hover:text-cyan-800 focus:outline-none focus:ring-2 focus:ring-cyan-200"
                      >
                        관제 상세
                      </button>
                    </div>

                    <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-100 pt-3 text-xs text-slate-500">
                      <span className="font-bold text-slate-700">{event.droneLabel}</span>
                      <time dateTime={event.occurredAt}>{formatKoreanDateTime(event.occurredAt)}</time>
                      <span>{relativeTime(event.occurredAt, nowMs)}</span>
                      {event.snapshotAvailable && <span className="font-bold text-violet-700">탐지 증적 있음</span>}
                    </div>
                  </article>
                </li>
              );
            })}
          </ol>
        )}

        {filteredEvents.length > DISPLAY_LIMIT && (
          <p className="mt-4 rounded-xl bg-slate-50 px-4 py-3 text-center text-xs font-bold text-slate-500">
            최신 {DISPLAY_LIMIT}건만 표시 중입니다. 필터를 추가해 범위를 좁혀주세요.
          </p>
        )}
      </section>

      {selectedEvent && (
        <EventDetailDrawer
          event={selectedEvent}
          returnFocusElement={returnFocusElement}
          onClose={closeDetail}
        />
      )}
    </div>
  );
}

function SummaryCard({
  label,
  value,
  unit,
  tone,
}: {
  label: string;
  value: number;
  unit: string;
  tone: "rose" | "cyan" | "amber" | "violet";
}) {
  const toneClass = {
    rose: "border-rose-300/20 bg-rose-400/10",
    cyan: "border-cyan-300/20 bg-cyan-400/10",
    amber: "border-amber-300/20 bg-amber-400/10",
    violet: "border-violet-300/20 bg-violet-400/10",
  }[tone];

  return (
    <article className={`rounded-2xl border p-4 ${toneClass}`}>
      <p className="text-xs font-bold text-slate-300">{label}</p>
      <p className="mt-2 text-3xl font-black text-white">
        {value}<span className="ml-1 text-sm text-slate-400">{unit}</span>
      </p>
    </article>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-xs font-black text-slate-500">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none transition focus:border-cyan-600 focus:ring-2 focus:ring-cyan-100"
      >
        {children}
      </select>
    </label>
  );
}
