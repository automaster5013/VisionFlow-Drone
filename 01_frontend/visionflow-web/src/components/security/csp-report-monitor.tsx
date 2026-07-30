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
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-violet-700">
            CSP REPORT-ONLY OBSERVABILITY
          </p>
          <h2 className="mt-1 text-xl font-black text-slate-950">
            CSP 위반 관찰 현황
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
            브라우저 요청은 차단하지 않습니다. 쿼리 문자열을 제거한 정제 보고서만
            프로세스 메모리에 최대 50건 보관하며 서버 재시작 시 초기화됩니다.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`rounded-full border px-3 py-1 text-xs font-bold ${
              state.phase === "loading"
                ? "border-slate-200 bg-slate-50 text-slate-600"
                : state.phase === "error"
                  ? "border-rose-200 bg-rose-50 text-rose-700"
                  : hasReports
                    ? "border-amber-200 bg-amber-50 text-amber-800"
                    : "border-emerald-200 bg-emerald-50 text-emerald-700"
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
            className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50"
          >
            새로고침
          </button>
        </div>
      </div>

      {state.error ? (
        <p className="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {state.error}
        </p>
      ) : null}

      {data ? (
        <>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <article className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-bold text-slate-500">전체 수신</p>
              <p className="mt-1 text-2xl font-black text-slate-950">
                {data.totalReports}건
              </p>
            </article>
            <article className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-bold text-slate-500">현재 보관</p>
              <p className="mt-1 text-2xl font-black text-slate-950">
                {data.retainedReports}/{data.maxRetainedReports}건
              </p>
            </article>
            <article className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <p className="text-xs font-bold text-slate-500">마지막 수신</p>
              <p className="mt-1 text-sm font-black text-slate-950">
                {formatTimestamp(data.lastReceivedAt)}
              </p>
            </article>
          </div>

          <div className="mt-5 grid gap-5 lg:grid-cols-[0.8fr_1.2fr]">
            <div>
              <h3 className="text-sm font-black text-slate-950">
                지시문별 보관 건수
              </h3>
              {data.byDirective.length > 0 ? (
                <ul className="mt-3 space-y-2">
                  {data.byDirective.map((item) => (
                    <li
                      key={item.directive}
                      className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    >
                      <code className="text-slate-700">{item.directive}</code>
                      <span className="font-black text-slate-950">
                        {item.count}건
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 rounded-lg bg-emerald-50 p-4 text-sm text-emerald-800">
                  현재까지 수신된 CSP 위반이 없습니다.
                </p>
              )}
            </div>

            <div>
              <h3 className="text-sm font-black text-slate-950">
                최근 위반 내역
              </h3>
              {data.reports.length > 0 ? (
                <ul className="mt-3 max-h-96 space-y-3 overflow-y-auto pr-1">
                  {data.reports.map((report, index) => (
                    <li
                      key={`${report.receivedAt}-${index}`}
                      className="rounded-xl border border-amber-200 bg-amber-50/60 p-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <code className="text-xs font-bold text-amber-900">
                          {report.effectiveDirective ?? "unknown"}
                        </code>
                        <span className="text-xs text-slate-500">
                          {formatTimestamp(report.receivedAt)}
                        </span>
                      </div>
                      <p className="mt-2 break-all text-xs text-slate-700">
                        차단 후보: {report.blockedUri ?? "정보 없음"}
                      </p>
                      <p className="mt-1 break-all text-xs text-slate-500">
                        위치: {locationLabel(report)}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
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
