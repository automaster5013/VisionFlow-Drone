"use client";

import { useCallback, useEffect, useState } from "react";

interface HeaderCheck {
  name: string;
  expected: string;
  actual: string;
  passed: boolean;
}

type ProbeState =
  | { phase: "loading"; checks: HeaderCheck[]; error: null }
  | { phase: "ready"; checks: HeaderCheck[]; error: null }
  | { phase: "error"; checks: HeaderCheck[]; error: string };

const exactHeaders = [
  ["X-Content-Type-Options", "nosniff"],
  ["X-Frame-Options", "DENY"],
  ["Referrer-Policy", "strict-origin-when-cross-origin"],
  ["Cross-Origin-Opener-Policy", "same-origin"],
  ["X-DNS-Prefetch-Control", "off"],
  ["X-Permitted-Cross-Domain-Policies", "none"],
] as const;

function inspectHeaders(headers: Headers): HeaderCheck[] {
  const checks: HeaderCheck[] = exactHeaders.map(([name, expected]) => {
    const actual = headers.get(name)?.trim() ?? "";
    return {
      name,
      expected,
      actual: actual || "<missing>",
      passed: actual.toLowerCase() === expected.toLowerCase(),
    };
  });
  const permissions = headers.get("Permissions-Policy")?.trim() ?? "";
  const compactPermissions = permissions.replace(/\s/g, "");
  checks.push({
    name: "Permissions-Policy",
    expected: "camera=(self), geolocation=(self), microphone=()",
    actual: permissions || "<missing>",
    passed:
      compactPermissions.includes("camera=(self)") &&
      compactPermissions.includes("geolocation=(self)") &&
      compactPermissions.includes("microphone=()"),
  });
  const cspReportOnly =
    headers.get("Content-Security-Policy-Report-Only")?.trim() ?? "";
  const normalizedCsp = cspReportOnly.toLowerCase();
  checks.push({
    name: "Content-Security-Policy-Report-Only",
    expected: "report-only policy with /api/security/csp-report",
    actual: cspReportOnly || "<missing>",
    passed:
      normalizedCsp.includes("default-src 'self'") &&
      normalizedCsp.includes("object-src 'none'") &&
      normalizedCsp.includes("frame-ancestors 'none'") &&
      normalizedCsp.includes("report-uri /api/security/csp-report"),
  });
  const poweredBy = headers.get("X-Powered-By")?.trim() ?? "";
  checks.push({
    name: "X-Powered-By",
    expected: "<absent>",
    actual: poweredBy || "<absent>",
    passed: poweredBy.length === 0,
  });
  return checks;
}

export function SecurityHeaderProbe() {
  const [state, setState] = useState<ProbeState>({
    phase: "loading",
    checks: [],
    error: null,
  });

  const probe = useCallback((signal?: AbortSignal) => {
    return fetch("/dashboard", {
      method: "GET",
      cache: "no-store",
      headers: { Accept: "text/html" },
      signal,
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`대시보드 응답이 HTTP ${response.status}입니다.`);
        }
        setState({
          phase: "ready",
          checks: inspectHeaders(response.headers),
          error: null,
        });
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState({
          phase: "error",
          checks: [],
          error:
            error instanceof Error
              ? error.message
              : "보안 응답 헤더를 확인할 수 없습니다.",
        });
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void probe(controller.signal);
    return () => controller.abort();
  }, [probe]);

  const passedCount = state.checks.filter((check) => check.passed).length;
  const allPassed =
    state.phase === "ready" && passedCount === state.checks.length;

  return (
    <section className="vf-security-command__panel rounded-2xl border p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="vf-security-command__eyebrow text-sm font-semibold">
            BROWSER HARDENING
          </p>
          <h2 className="vf-security-command__section-title mt-1 text-xl font-black">
            프런트엔드 보안 응답 헤더
          </h2>
          <p className="vf-security-command__detail mt-2 text-sm">
            현재 브라우저가 받은 실제 대시보드 응답을 검사합니다.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`rounded-full border px-3 py-1 text-xs font-bold ${
              state.phase === "loading"
                ? "vf-security-command__badge--loading"
                : allPassed
                  ? "vf-security-command__badge--good"
                  : "vf-security-command__badge--danger"
            }`}
          >
            {state.phase === "loading"
              ? "검사 중"
              : allPassed
                ? `${passedCount}/${state.checks.length} PASS`
                : "확인 필요"}
          </span>
          <button
            type="button"
            onClick={() => {
              setState({ phase: "loading", checks: [], error: null });
              void probe();
            }}
            className="vf-security-command__button rounded-lg border px-3 py-2 text-xs font-bold"
          >
            다시 검사
          </button>
        </div>
      </div>

      {state.error ? (
        <p className="vf-security-command__notice vf-security-command__notice--danger mt-5 rounded-xl border p-4 text-sm">
          {state.error}
        </p>
      ) : null}

      <div className="mt-5 grid gap-3 md:grid-cols-2">
        {state.checks.map((check) => (
          <article
            key={check.name}
            className={`rounded-xl border p-4 ${
              check.passed
                ? "vf-security-command__check--good"
                : "vf-security-command__check--danger"
            }`}
          >
            <div className="flex items-center justify-between gap-3">
              <p className="vf-security-command__check-name text-sm font-bold">
                {check.name}
              </p>
              <span
                className={`text-xs font-black ${
                  check.passed
                    ? "vf-security-command__result--good"
                    : "vf-security-command__result--danger"
                }`}
              >
                {check.passed ? "PASS" : "FAIL"}
              </span>
            </div>
            <p className="vf-security-command__detail mt-2 break-all text-xs">
              실제값:{" "}
              {check.actual.length > 220
                ? `${check.actual.slice(0, 220)}…`
                : check.actual}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
