"use client";

import { useMemo, useState } from "react";

import type { AiInferenceEvent } from "@/types/ai-inference-event";
import type { Drone } from "@/types/drone";

interface AiInferenceEventPanelProps {
  events: AiInferenceEvent[];
  drones: Drone[];
  selectedDroneId: number | null;
  loadError: string | null;
  onRefresh: () => Promise<void>;
  onSelectDrone: (droneId: number) => void;
}

function formatDateTime(value: string): string {
  const date = new Date(value);

  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("ko-KR");
}

function sourceLabel(sourceType: AiInferenceEvent["sourceType"]): string {
  switch (sourceType) {
    case "SMARTPHONE_LIVE":
      return "스마트폰 라이브";
    case "DJI_LIVE":
      return "DJI 라이브";
    default:
      return "더미 영상";
  }
}

function formatNumber(value: number, fractionDigits = 1): string {
  const numericValue = Number(value);

  return Number.isFinite(numericValue)
    ? numericValue.toFixed(fractionDigits)
    : "-";
}

export function AiInferenceEventPanel({
  events,
  drones,
  selectedDroneId,
  loadError,
  onRefresh,
  onSelectDrone,
}: AiInferenceEventPanelProps) {
  const [selectedOnly, setSelectedOnly] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [previewEvent, setPreviewEvent] =
    useState<AiInferenceEvent | null>(null);
  const [deletingEventId, setDeletingEventId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const droneNameById = useMemo(
    () => new Map(drones.map((drone) => [drone.id, drone.name])),
    [drones],
  );

  const displayedEvents = useMemo(() => {
    const filtered =
      selectedOnly && selectedDroneId !== null
        ? events.filter((event) => event.droneId === selectedDroneId)
        : events;

    return filtered.slice(0, 12);
  }, [events, selectedDroneId, selectedOnly]);

  const displayedDetectionCount = displayedEvents.reduce(
    (total, event) => total + event.detectionCount,
    0,
  );

  async function handleRefresh() {
    if (refreshing) {
      return;
    }

    setRefreshing(true);

    try {
      await onRefresh();
    } catch {
      // 훅이 사용자에게 표시할 오류 상태를 이미 갱신합니다.
    } finally {
      setRefreshing(false);
    }
  }

  async function handleDeleteSnapshot(event: AiInferenceEvent) {
    if (deletingEventId !== null || !event.snapshotAvailable) {
      return;
    }

    if (
      !window.confirm(
        "이 저장 스냅샷을 영구 삭제합니다. 탐지 이벤트와 bbox 메타데이터는 유지됩니다. 계속하시겠습니까?",
      )
    ) {
      return;
    }

    setDeletingEventId(event.id);
    setDeleteError(null);

    try {
      const response = await fetch(`/api/ai/events/${event.id}/snapshot`, {
        method: "DELETE",
        headers: { Accept: "application/json" },
      });

      if (!response.ok) {
        let message = `스냅샷 삭제 실패: HTTP ${response.status}`;

        try {
          const payload: unknown = await response.json();
          if (
            typeof payload === "object" &&
            payload !== null &&
            "message" in payload &&
            typeof payload.message === "string"
          ) {
            message = payload.message;
          }
        } catch {
          // JSON 오류 본문이 아니면 HTTP 상태 메시지를 유지합니다.
        }

        throw new Error(message);
      }

      if (previewEvent?.id === event.id) {
        setPreviewEvent(null);
      }
      await onRefresh();
    } catch (error) {
      setDeleteError(
        error instanceof Error
          ? error.message
          : "스냅샷을 삭제하지 못했습니다.",
      );
    } finally {
      setDeletingEventId(null);
    }
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-bold text-slate-900">
              AI 영상 분석 이벤트
            </h2>

            <span className="rounded-full bg-violet-100 px-2.5 py-1 text-xs font-bold text-violet-700">
              최근 {displayedEvents.length}프레임
            </span>

            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">
              객체 {displayedDetectionCount}개
            </span>
          </div>

          <p className="mt-1 text-sm text-slate-500">
            저장된 최근 분석 결과와 STOMP 실시간 이벤트를 함께 표시합니다.
          </p>
          <p className="mt-1 text-xs font-medium text-rose-700">
            저장 스냅샷은 개인영상정보를 포함할 수 있습니다. 불필요한 이미지는 즉시 삭제하세요.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setSelectedOnly(true)}
            disabled={selectedDroneId === null}
            className={`rounded-lg border px-3 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-40 ${
              selectedOnly
                ? "border-violet-500 bg-violet-50 text-violet-700"
                : "border-slate-300 text-slate-600"
            }`}
          >
            선택 드론
          </button>

          <button
            type="button"
            onClick={() => setSelectedOnly(false)}
            className={`rounded-lg border px-3 py-2 text-sm font-semibold ${
              !selectedOnly
                ? "border-violet-500 bg-violet-50 text-violet-700"
                : "border-slate-300 text-slate-600"
            }`}
          >
            전체 드론
          </button>

          <button
            type="button"
            onClick={() => void handleRefresh()}
            disabled={refreshing}
            className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-60"
          >
            {refreshing ? "조회 중" : "새로고침"}
          </button>
        </div>
      </div>

      {loadError && (
        <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-800">
          AI 이벤트를 불러오지 못했습니다: {loadError}
        </div>
      )}

      {deleteError && (
        <div className="mt-4 rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-800">
          {deleteError}
        </div>
      )}

      {displayedEvents.length === 0 ? (
        <div className="mt-4 rounded-xl bg-slate-50 p-6 text-center text-sm text-slate-500">
          {selectedOnly && selectedDroneId !== null
            ? "선택한 드론의 AI 탐지 이벤트가 아직 없습니다."
            : "AI 탐지 이벤트가 아직 없습니다."}
        </div>
      ) : (
        <div className="mt-4 grid gap-3 xl:grid-cols-2">
          {displayedEvents.map((event, eventIndex) => (
            <article
              key={event.id}
              className={`rounded-xl border p-4 ${
                eventIndex === 0
                  ? "border-violet-300 bg-violet-50/40"
                  : "border-slate-200"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <button
                    type="button"
                    onClick={() => onSelectDrone(event.droneId)}
                    className="text-left font-semibold text-slate-900 hover:text-violet-700"
                  >
                    {droneNameById.get(event.droneId) ??
                      `${event.droneId}번 드론`}
                  </button>

                  <div className="mt-1 text-xs text-slate-500">
                    {sourceLabel(event.sourceType)} · 프레임 {event.frameIndex}{" "}
                    · {formatDateTime(event.capturedAt)}
                  </div>
                </div>

                <div className="flex flex-col items-end gap-2 text-right">
                  <div>
                    <div className="text-sm font-bold text-violet-700">
                      {event.detectionCount}개 탐지
                    </div>
                    <div className="text-xs text-slate-500">
                      추론 {formatNumber(event.inferenceMs, 2)}ms
                    </div>
                  </div>

                  {event.snapshotAvailable && (
                    <button
                      type="button"
                      onClick={() => void handleDeleteSnapshot(event)}
                      disabled={deletingEventId !== null}
                      className="rounded-lg border border-rose-300 bg-white px-2.5 py-1.5 text-xs font-bold text-rose-700 transition hover:bg-rose-50 disabled:cursor-wait disabled:opacity-50"
                    >
                      {deletingEventId === event.id ? "삭제 중" : "스냅샷 삭제"}
                    </button>
                  )}
                </div>
              </div>

              {event.snapshotAvailable && event.snapshotUrl ? (
                <button
                  type="button"
                  onClick={() => setPreviewEvent(event)}
                  className="mt-3 block w-full overflow-hidden rounded-lg border border-slate-200 bg-slate-950 text-left transition hover:border-violet-400"
                  aria-label={`${event.frameIndex}번 프레임 분석 이미지 크게 보기`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={event.snapshotUrl}
                    alt={`AI 탐지 프레임 ${event.frameIndex}`}
                    loading="lazy"
                    className="aspect-video w-full object-contain"
                  />

                  <span className="block bg-slate-900 px-3 py-2 text-xs font-semibold text-white">
                    저장된 분석 장면 크게 보기
                  </span>
                </button>
              ) : (
                <div className="mt-3 flex aspect-video items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 text-center text-xs text-slate-500">
                  이 이벤트에는 저장된 분석 이미지가 없습니다.
                </div>
              )}

              <div className="mt-3 space-y-2">
                {event.detections.map((detection) => (
                  <div
                    key={detection.id}
                    className="rounded-lg border border-slate-200 bg-white px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="font-semibold text-slate-800">
                        {detection.className}
                      </span>

                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-bold ${
                          Number(detection.confidence) >= 0.8
                            ? "bg-emerald-100 text-emerald-700"
                            : "bg-amber-100 text-amber-700"
                        }`}
                      >
                        {formatNumber(Number(detection.confidence) * 100, 1)}%
                      </span>
                    </div>

                    <div className="mt-1 text-xs text-slate-500">
                      bbox [{formatNumber(detection.x1)},{" "}
                      {formatNumber(detection.y1)}]{" → "}[
                      {formatNumber(detection.x2)}, {formatNumber(detection.y2)}
                      ]
                    </div>
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>
      )}

      {previewEvent?.snapshotUrl && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="AI 탐지 장면 상세 보기"
          className="fixed inset-0 z-[1000] flex items-center justify-center bg-slate-950/80 p-4"
          onClick={() => setPreviewEvent(null)}
        >
          <div
            className="w-full max-w-5xl overflow-hidden rounded-2xl bg-white shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4 border-b border-slate-200 p-4">
              <div>
                <div className="font-bold text-slate-900">
                  {droneNameById.get(previewEvent.droneId) ??
                    `${previewEvent.droneId}번 드론`} · 프레임 {previewEvent.frameIndex}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {formatDateTime(previewEvent.capturedAt)} · 객체 {previewEvent.detectionCount}개
                </div>
              </div>

              <button
                type="button"
                onClick={() => setPreviewEvent(null)}
                className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white"
              >
                닫기
              </button>
            </div>

            <div className="bg-slate-950">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={previewEvent.snapshotUrl}
                alt={`AI 탐지 프레임 ${previewEvent.frameIndex} 상세`}
                className="max-h-[75vh] w-full object-contain"
              />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
