"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { useOperatorAccess } from "@/components/security/operator-access-provider";
import {
  isPersistedFlightQualityBackfillResponse,
  type PersistedFlightQualityBackfillResponse,
} from "@/types/flight-quality-assessment";
import {
  extractFleetReliabilityResponse,
  type FleetDroneReliability,
  type FleetReliabilityResponse,
  type FleetReliabilityStatus,
} from "@/types/fleet-reliability";

type SortMode = "RISK" | "SCORE" | "SESSIONS";

interface ReliabilityLoadState {
  resolved: boolean;
  response: FleetReliabilityResponse | null;
  errorMessage: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
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

function timestamp(value: string): number {
  const parsed = new Date(
    value.replace(/(\.\d{3})\d+(?=Z|[+-]\d{2}:\d{2}|$)/, "$1"),
  ).getTime();

  return Number.isNaN(parsed) ? 0 : parsed;
}

function formatDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds));
  const hours = Math.floor(seconds / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);

  return hours > 0
    ? `${hours}시간 ${minutes}분`
    : `${minutes}분 ${seconds % 60}초`;
}

function formatDateTime(value: string): string {
  const parsed = timestamp(value);

  return parsed > 0 ? new Date(parsed).toLocaleString("ko-KR") : value;
}

function signedScoreDelta(
  current: number,
  previous: number | null,
): string {
  if (previous === null) {
    return "이전 비행 없음";
  }

  const delta = current - previous;

  return `직전 대비 ${delta > 0 ? "+" : ""}${delta}점`;
}

function statusPresentation(status: FleetReliabilityStatus) {
  return {
    STABLE: {
      label: "안정",
      className: "border-emerald-200 bg-emerald-50 text-emerald-800",
      badgeClassName: "bg-emerald-600 text-white",
    },
    WATCH: {
      label: "관찰",
      className: "border-amber-200 bg-amber-50 text-amber-900",
      badgeClassName: "bg-amber-500 text-white",
    },
    CHECK: {
      label: "점검 필요",
      className: "border-rose-200 bg-rose-50 text-rose-900",
      badgeClassName: "bg-rose-600 text-white",
    },
  }[status];
}

function reportHref(droneId: number, sessionId: string): string {
  return (
    `/drones/${droneId}/flight-sessions/` +
    `${encodeURIComponent(sessionId)}/report`
  );
}

function csvCell(value: string | number): string {
  let text = String(value);

  if (/^[=+\-@]/.test(text)) {
    text = `'${text}`;
  }

  return `"${text.replaceAll('"', '""')}"`;
}

function downloadText(
  filename: string,
  content: string,
  contentType: string,
): void {
  const blob = new Blob([content], { type: contentType });
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");

  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.hidden = true;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

export function FleetReliabilityDashboard() {
  const { canOperate, operateDeniedReason } = useOperatorAccess();
  const [sortMode, setSortMode] = useState<SortMode>("RISK");
  const [reloadToken, setReloadToken] = useState(0);
  const [backfillLoading, setBackfillLoading] = useState(false);
  const [backfillMessage, setBackfillMessage] = useState<string | null>(null);
  const [backfillError, setBackfillError] = useState<string | null>(null);
  const [state, setState] = useState<ReliabilityLoadState>({
    resolved: false,
    response: null,
    errorMessage: null,
  });

  useEffect(() => {
    const abortController = new AbortController();

    fetch("/api/flight-quality/fleet-reliability?limitPerDrone=20", {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal: abortController.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(
            await readErrorMessage(
              response,
              `함대 운영 신뢰도 조회 실패: ${response.status}`,
            ),
          );
        }

        const payload: unknown = await response.json();
        const reliability = extractFleetReliabilityResponse(payload);

        if (reliability === null) {
          throw new Error("함대 운영 신뢰도 응답 형식이 올바르지 않습니다.");
        }

        if (abortController.signal.aborted) {
          return;
        }

        setState({
          resolved: true,
          response: reliability,
          errorMessage: null,
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
          resolved: true,
          response: null,
          errorMessage:
            loadError instanceof Error
              ? loadError.message
              : "기체별 운영 신뢰도를 조회하지 못했습니다.",
        });
      });

    return () => abortController.abort();
  }, [reloadToken]);

  const reliability = useMemo(
    () => state.response?.drones ?? [],
    [state.response],
  );
  const sortedReliability = useMemo(() => {
    const items = [...reliability];

    if (sortMode === "SCORE") {
      return items.sort(
        (left, right) => right.averageScore - left.averageScore,
      );
    }
    if (sortMode === "SESSIONS") {
      return items.sort(
        (left, right) => right.assessmentCount - left.assessmentCount,
      );
    }

    const statusOrder = { CHECK: 0, WATCH: 1, STABLE: 2 };

    return items.sort(
      (left, right) =>
        statusOrder[left.status] - statusOrder[right.status] ||
        left.averageScore - right.averageScore,
    );
  }, [reliability, sortMode]);
  const averageFleetScore = state.response?.fleetAverageScore ?? 0;
  const attentionCount = state.response?.attentionDroneCount ?? 0;
  const backfillDroneIds = state.response?.backfillCandidateDroneIds ?? [];

  async function backfillMissingAssessments() {
    if (!canOperate || backfillLoading || backfillDroneIds.length === 0) {
      return;
    }

    setBackfillLoading(true);
    setBackfillMessage(null);
    setBackfillError(null);

    try {
      const results = await Promise.allSettled(
        backfillDroneIds.map(async (droneId) => {
          const response = await fetch(
            `/api/drones/${droneId}` +
              "/flight-quality-assessments/backfill?limit=100&force=false",
            {
              method: "POST",
              headers: { Accept: "application/json" },
              cache: "no-store",
            },
          );

          if (!response.ok) {
            throw new Error(
              await readErrorMessage(
                response,
                `Drone #${droneId} 백필 실패: ${response.status}`,
              ),
            );
          }

          const payload: unknown = await response.json();

          if (
            !isPersistedFlightQualityBackfillResponse(payload) ||
            payload.droneId !== droneId
          ) {
            throw new Error(
              `Drone #${droneId} 백필 응답 형식이 올바르지 않습니다.`,
            );
          }

          return payload;
        }),
      );
      const succeeded = results
        .filter(
          (
            result,
          ): result is PromiseFulfilledResult<PersistedFlightQualityBackfillResponse> =>
            result.status === "fulfilled",
        )
        .map((result) => result.value);
      const requestFailureCount = results.length - succeeded.length;
      const evaluatedCount = succeeded.reduce(
        (sum, result) => sum + result.evaluatedCount,
        0,
      );
      const skippedCount = succeeded.reduce(
        (sum, result) => sum + result.skippedCount,
        0,
      );
      const evaluationFailureCount = succeeded.reduce(
        (sum, result) => sum + result.failedCount,
        0,
      );

      if (requestFailureCount > 0 || evaluationFailureCount > 0) {
        setBackfillError(
          `저장 완료 ${evaluatedCount}개, 기존 평가 ${skippedCount}개, ` +
            `실패 ${requestFailureCount + evaluationFailureCount}개입니다.`,
        );
      } else {
        setBackfillMessage(
          evaluatedCount > 0
            ? `누락된 품질 평가 ${evaluatedCount}개를 MySQL에 저장했습니다.`
            : `모든 대상 세션이 이미 평가되어 있습니다. ${skippedCount}개를 확인했습니다.`,
        );
      }

      setReloadToken((current) => current + 1);
    } catch (backfillRequestError) {
      setBackfillError(
        backfillRequestError instanceof Error
          ? backfillRequestError.message
          : "기존 종료 세션의 품질 평가를 저장하지 못했습니다.",
      );
    } finally {
      setBackfillLoading(false);
    }
  }

  function exportJson() {
    downloadText(
      "visionflow-fleet-reliability.json",
      `${JSON.stringify(
        {
          schemaVersion: 1,
          project: "VisionFlow",
          evidenceType: "FLEET_OPERATIONAL_RELIABILITY",
          generatedAt: state.response?.generatedAt,
          aggregationSource: "BACKEND_MYSQL",
          ruleVersion: state.response?.ruleVersion,
          limitPerDrone: state.response?.limitPerDrone,
          evaluatedSessionCount: state.response?.assessmentCount ?? 0,
          fleetAverageScore: averageFleetScore,
          drones: reliability.map((item) => ({
            droneId: item.droneId,
            droneCode: item.droneCode,
            droneName: item.droneName,
            modelName: item.modelName,
            status: item.status,
            averageScore: item.averageScore,
            minimumScore: item.minimumScore,
            latestScore: item.latestScore,
            previousScore: item.previousScore,
            completedCount: item.completedCount,
            abortedCount: item.abortedCount,
            totalDurationSeconds: item.totalDurationSeconds,
            criticalCount: item.criticalCount,
            warningCount: item.warningCount,
            sessions: item.trend.map((point) => ({
              sessionId: point.sessionId,
              sessionName: point.sessionName,
              status: point.sessionStatus,
              startedAt: point.startedAt,
              endedAt: point.endedAt,
              durationSeconds: point.durationSeconds,
              assessmentSource: "BACKEND_MYSQL",
              quality: point.quality,
            })),
          })),
        },
        null,
        2,
      )}\n`,
      "application/json;charset=utf-8",
    );
  }

  function exportCsv() {
    const rows = [
      [
        "드론 ID",
        "상태",
        "평균 점수",
        "최저 점수",
        "최근 점수",
        "평가 세션",
        "완료",
        "중단",
        "위험",
        "주의",
        "누적 비행 초",
      ],
      ...reliability.map((item) => [
        item.droneId,
        statusPresentation(item.status).label,
        item.averageScore.toFixed(1),
        item.minimumScore,
        item.latestScore,
        item.assessmentCount,
        item.completedCount,
        item.abortedCount,
        item.criticalCount,
        item.warningCount,
        item.totalDurationSeconds,
      ]),
    ];
    const csv = rows
      .map((row) => row.map((value) => csvCell(value)).join(","))
      .join("\r\n");

    downloadText(
      "visionflow-fleet-reliability.csv",
      `\uFEFF${csv}\r\n`,
      "text/csv;charset=utf-8",
    );
  }

  return (
    <main className="min-h-screen bg-slate-100 px-4 py-8 print:bg-white print:p-0">
      <section className="mx-auto max-w-6xl">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-black uppercase tracking-[0.18em] text-cyan-700">
              Fleet Reliability
            </p>
            <h1 className="mt-2 text-3xl font-black text-slate-950">
              기체별 운영 신뢰도
            </h1>
            <p className="mt-2 text-sm text-slate-600">
              최근 완료·중단 비행을 드론별로 묶어 품질과 위험 이력을
              비교합니다.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 print:hidden">
            <Link
              href="/dashboard"
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700"
            >
              운영 대시보드
            </Link>
            <Link
              href="/maintenance"
              className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-bold text-amber-900"
            >
              점검 작업지시
            </Link>
            <button
              type="button"
              onClick={backfillMissingAssessments}
              disabled={
                !canOperate ||
                backfillLoading ||
                !state.resolved ||
                backfillDroneIds.length === 0
              }
              title={
                canOperate
                  ? "저장 평가가 없는 기존 종료 세션만 MySQL에 평가합니다."
                  : (operateDeniedReason ?? undefined)
              }
              className="rounded-lg border border-cyan-300 bg-cyan-50 px-4 py-2 text-sm font-bold text-cyan-900 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {backfillLoading ? "기존 평가 저장 중..." : "기존 평가 채우기"}
            </button>
            <button
              type="button"
              onClick={exportJson}
              disabled={!state.resolved || reliability.length === 0}
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-800 disabled:opacity-50"
            >
              JSON
            </button>
            <button
              type="button"
              onClick={exportCsv}
              disabled={!state.resolved || reliability.length === 0}
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-800 disabled:opacity-50"
            >
              CSV
            </button>
            <button
              type="button"
              onClick={() => window.print()}
              disabled={!state.resolved || reliability.length === 0}
              className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
            >
              인쇄 / PDF
            </button>
          </div>
        </header>

        {(backfillMessage || backfillError) && (
          <div className="mt-4 print:hidden">
            {backfillMessage && (
              <p
                role="status"
                className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-bold text-emerald-900"
              >
                {backfillMessage}
              </p>
            )}
            {backfillError && (
              <p
                role="alert"
                className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-bold text-red-900"
              >
                {backfillError}
              </p>
            )}
          </div>
        )}

        {!state.resolved ? (
          <ReliabilityNotice>
            MySQL 품질 평가를 백엔드에서 기체별로 집계하고 있습니다.
          </ReliabilityNotice>
        ) : state.errorMessage ? (
          <div
            role="alert"
            className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-5 text-red-900"
          >
            {state.errorMessage}
          </div>
        ) : reliability.length === 0 ? (
          <ReliabilityNotice>
            저장된 품질 평가가 없습니다. 종료 비행이 있다면 상단의
            &apos;기존 평가 채우기&apos;로 MySQL 평가를 생성하세요.
          </ReliabilityNotice>
        ) : (
          <>
            <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <FleetMetric
                label="평가 기체"
                value={`${reliability.length}대`}
                description="백엔드 MySQL 단일 집계"
              />
              <FleetMetric
                label="기체 평균 점수"
                value={`${averageFleetScore.toFixed(1)}점`}
                description="기체별 평균의 전체 평균"
              />
              <FleetMetric
                label="우선 확인 기체"
                value={`${attentionCount}대`}
                description="관찰 또는 점검 필요"
              />
              <FleetMetric
                label="저장 품질 평가"
                value={`${state.response?.assessmentCount ?? 0}개`}
                description={formatDateTime(
                  state.response?.generatedAt ?? "",
                )}
              />
            </div>

            <div className="mt-6 flex flex-wrap items-center justify-between gap-3 print:hidden">
              <div className="text-sm font-bold text-slate-700">
                기체 {reliability.length}대를 분석했습니다.
              </div>
              <label className="text-sm font-bold text-slate-700">
                정렬
                <select
                  value={sortMode}
                  onChange={(event) =>
                    setSortMode(event.target.value as SortMode)
                  }
                  className="ml-2 rounded-lg border border-slate-300 bg-white px-3 py-2 font-normal"
                >
                  <option value="RISK">위험 우선</option>
                  <option value="SCORE">평균 점수 높은 순</option>
                  <option value="SESSIONS">평가 세션 많은 순</option>
                </select>
              </label>
            </div>

            <div className="mt-4 grid gap-5 lg:grid-cols-2">
              {sortedReliability.map((item) => (
                <DroneReliabilityCard key={item.droneId} item={item} />
              ))}
            </div>

            <p className="mt-6 rounded-xl bg-white p-4 text-xs leading-5 text-slate-500">
              MySQL에 저장된 기체별 최근 품질 평가 최대{" "}
              {state.response?.limitPerDrone ?? 20}개를 백엔드가 집계한 운영
              보조 지표입니다. 실제 기체 정비 판정이나 항공 안전 인증을
              대신하지 않습니다.
            </p>
          </>
        )}
      </section>
    </main>
  );
}

function ReliabilityNotice({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-6 rounded-2xl bg-white p-6 text-sm text-slate-600 shadow-sm">
      {children}
    </div>
  );
}

function FleetMetric({
  label,
  value,
  description,
}: {
  label: string;
  value: string;
  description: string;
}) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="text-sm font-bold text-slate-500">{label}</div>
      <div className="mt-2 text-3xl font-black text-slate-950">{value}</div>
      <div className="mt-2 text-xs text-slate-500">{description}</div>
    </article>
  );
}

function DroneReliabilityCard({ item }: { item: FleetDroneReliability }) {
  const presentation = statusPresentation(item.status);
  const scoreWidth = `${Math.max(0, Math.min(100, item.averageScore))}%`;

  return (
    <article
      className={`break-inside-avoid rounded-2xl border p-5 shadow-sm ${presentation.className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-black text-slate-950">
            {item.droneName ?? `Drone #${item.droneId}`}
          </h2>
          <div className="mt-1 text-xs">
            {item.droneCode ?? `ID ${item.droneId}`} · 최근{" "}
            {item.assessmentCount}개 평가 기준
          </div>
          <div className="mt-1 text-[11px] font-bold">
            최근 평가: 백엔드 MySQL 집계
          </div>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-black ${presentation.badgeClassName}`}
        >
          {presentation.label}
        </span>
      </div>

      <div className="mt-5 flex items-end justify-between gap-3">
        <div>
          <div className="text-xs font-bold">평균 품질 점수</div>
          <div className="mt-1 text-4xl font-black text-slate-950">
            {item.averageScore.toFixed(1)}
          </div>
        </div>
        <div className="text-right text-xs font-bold">
          <div>최근 {item.latestScore}점</div>
          <div className="mt-1">
            {signedScoreDelta(item.latestScore, item.previousScore)}
          </div>
        </div>
      </div>

      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/70">
        <div
          className="h-full rounded-full bg-slate-900"
          style={{ width: scoreWidth }}
        />
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
        <ReliabilityValue
          label="완료 / 중단"
          value={`${item.completedCount} / ${item.abortedCount}`}
        />
        <ReliabilityValue
          label="위험 / 주의"
          value={`${item.criticalCount} / ${item.warningCount}`}
        />
        <ReliabilityValue
          label="최저 점수"
          value={`${item.minimumScore}점`}
        />
        <ReliabilityValue
          label="누적 비행"
          value={formatDuration(item.totalDurationSeconds)}
        />
      </div>

      {item.latestAssessment.primaryRisk && (
        <div className="mt-4 rounded-xl bg-white/70 p-3 text-xs">
          <div className="font-black text-slate-900">최근 주요 진단</div>
          <div className="mt-1 font-bold">
            {item.latestAssessment.primaryRisk.title}
          </div>
          <div className="mt-1 text-slate-600">
            {item.latestAssessment.primaryRisk.detail}
          </div>
        </div>
      )}

      <div className="mt-4 flex flex-wrap justify-end gap-2 print:hidden">
        <Link
          href={`/drones?droneId=${item.droneId}`}
          className="rounded-lg border border-slate-400 bg-white px-3 py-2 text-xs font-bold text-slate-800"
        >
          드론 관제
        </Link>
        <Link
          href={reportHref(
            item.droneId,
            item.latestAssessment.sessionId,
          )}
          className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-bold text-white"
        >
          최근 진단 보고서
        </Link>
      </div>
    </article>
  );
}

function ReliabilityValue({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg bg-white/70 p-3">
      <div className="text-[10px] font-bold text-slate-500">{label}</div>
      <div className="mt-1 font-black text-slate-900">{value}</div>
    </div>
  );
}
