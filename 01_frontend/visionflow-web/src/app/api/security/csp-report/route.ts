import { type NextRequest, NextResponse } from "next/server";

import { requireOperatorApiAccess } from "@/lib/server/operator-api-access";

export const runtime = "nodejs";

const MAX_REPORT_BYTES = 16 * 1024;
const MAX_FIELD_LENGTH = 512;
const MAX_RETAINED_REPORTS = 50;

type UnknownRecord = Record<string, unknown>;

interface SanitizedCspReport {
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

interface CspReportStore {
  startedAt: string;
  totalReports: number;
  lastReceivedAt: string | null;
  reports: SanitizedCspReport[];
}

declare global {
  var visionFlowCspReportStore: CspReportStore | undefined;
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function firstReport(value: unknown): UnknownRecord | null {
  const root = Array.isArray(value) ? value[0] : value;
  if (!isRecord(root)) {
    return null;
  }
  const legacy = root["csp-report"];
  if (isRecord(legacy)) {
    return legacy;
  }
  if (isRecord(root.body)) {
    return root.body;
  }
  return root;
}

function readString(report: UnknownRecord, ...keys: string[]): string | null {
  for (const key of keys) {
    const value = report[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim().slice(0, MAX_FIELD_LENGTH);
    }
  }
  return null;
}

function readNumber(report: UnknownRecord, ...keys: string[]): number | null {
  for (const key of keys) {
    const value = report[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }
  return null;
}

function sanitizeUrl(value: string | null): string | null {
  if (!value) {
    return null;
  }
  try {
    const url = new URL(value);
    if (url.protocol === "http:" || url.protocol === "https:") {
      return `${url.origin}${url.pathname}`.slice(0, MAX_FIELD_LENGTH);
    }
    if (url.protocol === "blob:" || url.protocol === "data:") {
      return url.protocol;
    }
    return `${url.protocol}${url.pathname}`.slice(0, MAX_FIELD_LENGTH);
  } catch {
    const withoutQueryOrFragment = value.split(/[?#]/, 1)[0];
    return withoutQueryOrFragment.slice(0, MAX_FIELD_LENGTH);
  }
}

function sanitizeReport(report: UnknownRecord): SanitizedCspReport {
  return {
    documentUri: sanitizeUrl(
      readString(report, "document-uri", "documentURL", "documentUrl"),
    ),
    blockedUri: sanitizeUrl(
      readString(report, "blocked-uri", "blockedURL", "blockedUrl"),
    ),
    effectiveDirective: readString(
      report,
      "effective-directive",
      "effectiveDirective",
    ),
    violatedDirective: readString(
      report,
      "violated-directive",
      "violatedDirective",
    ),
    disposition: readString(report, "disposition"),
    sourceFile: sanitizeUrl(readString(report, "source-file", "sourceFile")),
    lineNumber: readNumber(report, "line-number", "lineNumber"),
    columnNumber: readNumber(report, "column-number", "columnNumber"),
    statusCode: readNumber(report, "status-code", "statusCode"),
    receivedAt: new Date().toISOString(),
  };
}

function getReportStore(): CspReportStore {
  globalThis.visionFlowCspReportStore ??= {
    startedAt: new Date().toISOString(),
    totalReports: 0,
    lastReceivedAt: null,
    reports: [],
  };
  return globalThis.visionFlowCspReportStore;
}

function retainReport(report: SanitizedCspReport) {
  const store = getReportStore();
  store.totalReports += 1;
  store.lastReceivedAt = report.receivedAt;
  store.reports.unshift(report);
  if (store.reports.length > MAX_RETAINED_REPORTS) {
    store.reports.length = MAX_RETAINED_REPORTS;
  }
}

function summarizeDirectives(reports: SanitizedCspReport[]) {
  const counts = new Map<string, number>();
  for (const report of reports) {
    const directive = report.effectiveDirective ?? "unknown";
    counts.set(directive, (counts.get(directive) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([directive, count]) => ({ directive, count }))
    .sort((left, right) => right.count - left.count || left.directive.localeCompare(right.directive));
}

export async function GET() {
  const access = await requireOperatorApiAccess("ADMIN");
  if (access) {
    return access;
  }

  const store = getReportStore();
  return NextResponse.json(
    {
      enabled: true,
      mode: "REPORT_ONLY",
      persisted: false,
      storage: "BOUNDED_PROCESS_MEMORY",
      maxReportBytes: MAX_REPORT_BYTES,
      maxRetainedReports: MAX_RETAINED_REPORTS,
      startedAt: store.startedAt,
      totalReports: store.totalReports,
      retainedReports: store.reports.length,
      lastReceivedAt: store.lastReceivedAt,
      byDirective: summarizeDirectives(store.reports),
      reports: store.reports,
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}

export async function POST(request: NextRequest) {
  const declaredLength = Number(request.headers.get("content-length") ?? "0");
  if (Number.isFinite(declaredLength) && declaredLength > MAX_REPORT_BYTES) {
    return NextResponse.json(
      {
        success: false,
        code: "CSP_REPORT_TOO_LARGE",
        message: "CSP 위반 보고서가 허용 크기를 초과했습니다.",
      },
      { status: 413, headers: { "Cache-Control": "no-store" } },
    );
  }

  const text = await request.text();
  if (Buffer.byteLength(text, "utf8") > MAX_REPORT_BYTES) {
    return NextResponse.json(
      {
        success: false,
        code: "CSP_REPORT_TOO_LARGE",
        message: "CSP 위반 보고서가 허용 크기를 초과했습니다.",
      },
      { status: 413, headers: { "Cache-Control": "no-store" } },
    );
  }

  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    return NextResponse.json(
      {
        success: false,
        code: "INVALID_CSP_REPORT",
        message: "CSP 위반 보고서 형식이 올바르지 않습니다.",
      },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }

  const report = firstReport(body);
  if (!report) {
    return NextResponse.json(
      {
        success: false,
        code: "INVALID_CSP_REPORT",
        message: "CSP 위반 보고서 본문을 확인할 수 없습니다.",
      },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }

  const sanitizedReport = sanitizeReport(report);
  retainReport(sanitizedReport);

  console.warn(
    "VisionFlow CSP report-only violation:",
    JSON.stringify(sanitizedReport),
  );

  return new NextResponse(null, {
    status: 204,
    headers: { "Cache-Control": "no-store" },
  });
}
