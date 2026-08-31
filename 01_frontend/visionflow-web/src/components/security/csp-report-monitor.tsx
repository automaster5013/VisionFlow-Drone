"use client";

import { useCallback, useEffect, useState } from "react";

interface CspReportItem {
  documentUri: string | null;
  blockedUri: string | null;
  effectiveDirective: string | null;
  violatedDirective: string | null;
  disposition: string | null;
  sourceFile: string | null;
  lineNumber: number | null;
  columnNumber: number | null;
  statusCode: number | null;
  receivedAt: string;
}

interface CspDirectiveCount {
  directive: string;
  count: number;
}

interface CspReportStatus {
  enabled: boolean;
  mode: "REPORT_ONLY";
  persisted: false;
  storage: "BOUNDED_PROCESS_MEMORY";
  maxReportBytes: number;
  maxRetainedReports: number;
  startedAt: string;
  totalReports: number;
  retainedReports: number;
  lastReceivedAt: string | null;
  byDirective: CspDirectiveCount[];
  reports: CspReportItem[];
}

type MonitorState =
  | { phase: "loading"; data: null; error: null }
  | { phase: "ready"; data: CspReportStatus; error: null }
  | { phase: "error"; data: null; error: string };

function formatTimestamp(value: string | null): string {
  if (!value) {
    return "수신 내역 없음";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(date);
}

function locationLabel(report: CspReportItem): string {
  if (report.sourceFile) {
    const line = report.lineNumber ? `:${report.lineNumber}` : "";
    const column = report.columnNumber ? `:${report.columnNumber}` : "";
    return `${report.sourceFile}${line}${column}`;
  }
  return report.documentUri ?? "위치 정보 없음";
}

export function CspReportMonitor() {
  const [state, setState] = useState<MonitorState>({
    phase: "loading",
    data: null,
    error: null,
  });

  const load = useCallback((signal?: AbortSignal) => {
    return fetch("/api/security/csp-report", {
      method: "GET",
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`CSP 관찰 상태 응답이 HTTP ${response.status}입니다.`);
        }
        const data = (await response.json()) as CspReportStatus;
        setState({ phase: "ready", data, error: null });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState({
          phase: "error",
          data: null,
          error:
            error instanceof Error
              ? error.message
              : "CSP 관찰 상태를 확인할 수 없습니다.",
        });
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    const intervalId = window.setInterval(() => {
      void load(controller.signal);
    }, 10_000);
    return () => {
      window.clearInterval(intervalId);
      controller.abort();
    };
  }, [load]);

  const data = state.data;
  const hasReports = (data?.totalReports ?? 0) > 0;

  return (
    <section className="vf-security-command__panel rounded-2xl border p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="vf-security-command__eyebrow text-sm font-semibold">
            CSP REPORT-ONLY OBSERVABILITY
          </p>
          <h2 className="vf-security-command__section-title mt-1 text-xl font-black">
            CSP 위반 관찰 현황
          </h2>
          <p className="vf-security-command__detail mt-2 max-w-3xl text-sm leading-6">
            브라우저 요청은 차단하지 않습니다. 쿼리 문자열을 제거한 정제 보고서만
            프로세스 메모리에 최대 50건 보관하며 서버 재시작 시 초기화됩니다.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`rounded-full border px-3 py-1 text-xs font-bold ${
              state.phase === "loading"
                ? "vf-security-command__badge--loading"
                : state.phase === "error"
                  ? "vf-security-command__badge--danger"
                  : hasReports
                    ? "vf-security-command__badge--warning"
                    : "vf-security-command__badge--good"
            }`}
          >
            {state.phase === "loading"
              ? "조회 중"
              : state.phase === "error"
                ? "조회 실패"
                : hasReports
                  ? "관찰 내역 있음"
                  : "위반 없음"}
          </span>
          <button
            type="button"
            onClick={() => {
              setState({ phase: "loading", data: null, error: null });
              void load();
            }}
            className="vf-security-command__button rounded-lg border px-3 py-2 text-xs font-bold"
          >
            새로고침
          </button>
        </div>
      </div>

      {state.error ? (
        <p className="vf-security-command__notice vf-security-command__notice--danger mt-5 rounded-xl border p-4 text-sm">
          {state.error}
        </p>
      ) : null}

      {data ? (
        <>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <article className="vf-security-command__metric rounded-xl border p-4">
              <p className="vf-security-command__label text-xs font-bold">전체 수신</p>
              <p className="vf-security-command__value mt-1 text-2xl font-black">
                {data.totalReports}건
              </p>
            </article>
            <article className="vf-security-command__metric rounded-xl border p-4">
              <p className="vf-security-command__label text-xs font-bold">현재 보관</p>
              <p className="vf-security-command__value mt-1 text-2xl font-black">
                {data.retainedReports}/{data.maxRetainedReports}건
              </p>
            </article>
            <article className="vf-security-command__metric rounded-xl border p-4">
              <p className="vf-security-command__label text-xs font-bold">마지막 수신</p>
              <p className="vf-security-command__value mt-1 text-sm font-black">
                {formatTimestamp(data.lastReceivedAt)}
              </p>
            </article>
          </div>

          <div className="mt-5 grid gap-5 lg:grid-cols-[0.8fr_1.2fr]">
            <div>
              <h3 className="vf-security-command__section-title text-sm font-black">
                지시문별 보관 건수
              </h3>
              {data.byDirective.length > 0 ? (
                <ul className="mt-3 space-y-2">
                  {data.byDirective.map((item) => (
                    <li
                      key={item.directive}
                      className="vf-security-command__directive flex items-center justify-between rounded-lg border px-3 py-2 text-sm"
                    >
                      <code className="vf-security-command__detail">{item.directive}</code>
                      <span className="vf-security-command__value font-black">
                        {item.count}건
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="vf-security-command__notice vf-security-command__notice--good mt-3 rounded-lg border p-4 text-sm">
                  현재까지 수신된 CSP 위반이 없습니다.
                </p>
              )}
            </div>

            <div>
              <h3 className="vf-security-command__section-title text-sm font-black">
                최근 위반 내역
              </h3>
              {data.reports.length > 0 ? (
                <ul className="mt-3 max-h-96 space-y-3 overflow-y-auto pr-1">
                  {data.reports.map((report, index) => (
                    <li
                      key={`${report.receivedAt}-${index}`}
                      className="vf-security-command__report rounded-xl border p-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <code className="vf-security-command__report-code text-xs font-bold">
                          {report.effectiveDirective ?? "unknown"}
                        </code>
                        <span className="vf-security-command__label text-xs">
                          {formatTimestamp(report.receivedAt)}
                        </span>
                      </div>
                      <p className="vf-security-command__detail mt-2 break-all text-xs">
                        차단 후보: {report.blockedUri ?? "정보 없음"}
                      </p>
                      <p className="vf-security-command__label mt-1 break-all text-xs">
                        위치: {locationLabel(report)}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="vf-security-command__notice mt-3 rounded-lg border p-4 text-sm">
                  최근 위반 내역이 없습니다.
                </p>
              )}
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}
