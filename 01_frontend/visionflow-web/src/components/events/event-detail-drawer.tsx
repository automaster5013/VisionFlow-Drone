"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

import { formatKoreanDateTime } from "@/lib/date";
import type {
  EventOperationsItem,
  EventOperationsSeverity,
  EventOperationsSource,
} from "@/types/event-operations";

interface EventDetailDrawerProps {
  event: EventOperationsItem;
  returnFocusElement: HTMLButtonElement | null;
  onClose: () => void;
}

const SOURCE_PRESENTATION: Record<
  EventOperationsSource,
  { label: string; eyebrow: string; badge: string }
> = {
  AI_ALERT: {
    label: "AI 경보",
    eyebrow: "AI Alert",
    badge: "border-rose-300/40 bg-rose-400/15 text-rose-100",
  },
  AI_INFERENCE: {
    label: "AI 추론",
    eyebrow: "AI Inference",
    badge: "border-violet-300/40 bg-violet-400/15 text-violet-100",
  },
  GEOFENCE: {
    label: "지오펜스",
    eyebrow: "Geofence Event",
    badge: "border-amber-300/40 bg-amber-400/15 text-amber-100",
  },
  INCIDENT: {
    label: "Incident",
    eyebrow: "Incident Operations",
    badge: "border-cyan-300/40 bg-cyan-400/15 text-cyan-100",
  },
};

const SEVERITY_PRESENTATION: Record<
  EventOperationsSeverity,
  { label: string; badge: string }
> = {
  INFO: {
    label: "정보",
    badge: "border-sky-300/40 bg-sky-400/15 text-sky-100",
  },
  WARNING: {
    label: "주의",
    badge: "border-amber-300/40 bg-amber-400/15 text-amber-100",
  },
  CRITICAL: {
    label: "긴급",
    badge: "border-rose-300/40 bg-rose-400/15 text-rose-100",
  },
};

function buildReplayHref(event: EventOperationsItem): string | null {
  if (!event.sessionId) return null;

  const params = new URLSearchParams({
    droneId: String(event.droneId),
    sessionId: event.sessionId,
  });

  if (event.incidentId !== null && event.incidentSourceType !== null) {
    params.set("incidentId", String(event.incidentId));
    params.set("incidentAt", event.occurredAt);
    params.set("incidentSource", event.incidentSourceType);
  }

  return `/drones?${params.toString()}`;
}

export function EventDetailDrawer({
  event,
  returnFocusElement,
  onClose,
}: EventDetailDrawerProps) {
  const drawerRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const source = SOURCE_PRESENTATION[event.source];
  const severity = SEVERITY_PRESENTATION[event.severity];
  const replayHref = buildReplayHref(event);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    function handleKeyDown(keyboardEvent: KeyboardEvent): void {
      if (keyboardEvent.key === "Escape") {
        keyboardEvent.preventDefault();
        onClose();
        return;
      }

      if (keyboardEvent.key !== "Tab") return;

      const focusableElements = drawerRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (!focusableElements || focusableElements.length === 0) return;

      const first = focusableElements[0];
      const last = focusableElements[focusableElements.length - 1];
      if (keyboardEvent.shiftKey && document.activeElement === first) {
        keyboardEvent.preventDefault();
        last.focus();
      } else if (!keyboardEvent.shiftKey && document.activeElement === last) {
        keyboardEvent.preventDefault();
        first.focus();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      returnFocusElement?.focus();
    };
  }, [onClose, returnFocusElement]);

  return (
    <div data-event-operations-detail-drawer className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="이벤트 관제 상세 닫기"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-slate-950/75 backdrop-blur-sm"
      />

      <aside
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="event-operations-drawer-title"
        className="relative h-full w-full max-w-xl overflow-y-auto border-l border-slate-700 bg-slate-950 text-white shadow-2xl shadow-black/60"
      >
        <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/95 px-5 py-4 backdrop-blur sm:px-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[11px] font-black uppercase tracking-[0.18em] text-cyan-300">
                Event Operations Detail
              </p>
              <h2
                id="event-operations-drawer-title"
                className="mt-1 text-2xl font-black"
              >
                {source.label} #{event.sourceId}
              </h2>
            </div>
            <button
              ref={closeButtonRef}
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-600 px-3 py-2 text-xs font-black text-slate-200 transition hover:border-cyan-300 hover:text-cyan-100 focus:outline-none focus:ring-2 focus:ring-cyan-300"
            >
              닫기
            </button>
          </div>
        </header>

        <div className="space-y-5 p-5 sm:p-6">
          <section className="rounded-2xl border border-slate-700 bg-slate-900/70 p-5">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full border px-3 py-1 text-xs font-black ${source.badge}`}>
                {source.eyebrow}
              </span>
              <span className={`rounded-full border px-3 py-1 text-xs font-black ${severity.badge}`}>
                {severity.label}
              </span>
              <span className="rounded-full border border-slate-600 bg-slate-950/70 px-3 py-1 text-xs font-black text-slate-200">
                {event.statusLabel}
              </span>
            </div>

            <h3 className="mt-4 text-xl font-black text-white">{event.title}</h3>
            <p className="mt-3 rounded-xl border border-slate-700 bg-slate-950/80 px-4 py-3 text-sm leading-6 text-slate-200">
              {event.summary}
            </p>
            <dl className="mt-4 grid gap-3 sm:grid-cols-2">
              <DetailValue label="기체" value={event.droneLabel} />
              <DetailValue label="발생 시각" value={formatKoreanDateTime(event.occurredAt)} />
              <DetailValue label="원본 상태" value={event.status} />
              <DetailValue
                label="세션"
                value={event.sessionId ? maskSessionId(event.sessionId) : "연결 세션 없음"}
              />
            </dl>
          </section>

          {event.snapshotAvailable && event.snapshotEventId !== null && (
            <section className="overflow-hidden rounded-2xl border border-slate-700 bg-slate-900/70">
              <div className="px-5 pt-5">
                <h3 className="text-sm font-black text-white">탐지 증적</h3>
                <p className="mt-1 text-xs text-slate-400">
                  인증된 동일 출처 프록시에서 제공하는 저장 프레임입니다.
                </p>
              </div>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`/api/ai/events/${event.snapshotEventId}/snapshot`}
                alt={`${event.title} 탐지 증적`}
                className="mt-4 aspect-video w-full bg-black object-contain"
              />
            </section>
          )}

          <section className="rounded-2xl border border-slate-700 bg-slate-900/70 p-5">
            <h3 className="text-sm font-black text-white">판정 근거</h3>
            <dl className="mt-4 grid gap-3 sm:grid-cols-2">
              {event.details.map((detail) => (
                <DetailValue key={detail.label} label={detail.label} value={detail.value} />
              ))}
            </dl>
          </section>

          <nav aria-label="이벤트 후속 관제 이동" className="grid gap-2 sm:grid-cols-2">
            <Link
              href={`/drones/${event.droneId}`}
              className="rounded-xl border border-slate-600 px-4 py-3 text-center text-sm font-black text-slate-100 transition hover:border-cyan-300 hover:text-cyan-100"
            >
              기체 상세 보기
            </Link>
            {replayHref && (
              <Link
                href={replayHref}
                className="rounded-xl border border-violet-300/50 bg-violet-400/10 px-4 py-3 text-center text-sm font-black text-violet-100 transition hover:bg-violet-400/20"
              >
                세션 리플레이 열기
              </Link>
            )}
            {event.incidentId !== null && (
              <Link
                href={`/incidents/${event.incidentId}/report`}
                className="rounded-xl bg-cyan-400 px-4 py-3 text-center text-sm font-black text-slate-950 transition hover:bg-cyan-300 sm:col-span-2"
              >
                Incident 보고서 보기
              </Link>
            )}
          </nav>
        </div>
      </aside>
    </div>
  );
}

function DetailValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-950/70 px-4 py-3">
      <dt className="text-[11px] font-black text-slate-500">{label}</dt>
      <dd className="mt-1 break-words text-sm font-bold text-slate-100">{value}</dd>
    </div>
  );
}

function maskSessionId(sessionId: string): string {
  return sessionId.length <= 14
    ? sessionId
    : `${sessionId.slice(0, 8)}…${sessionId.slice(-4)}`;
}
