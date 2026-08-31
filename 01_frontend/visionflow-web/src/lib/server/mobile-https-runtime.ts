import "server-only";

import { lstat, readFile } from "node:fs/promises";
import { isIP } from "node:net";
import path from "node:path";

import type {
  MobileHttpsRuntimeCertificate,
  MobileHttpsRuntimeHealth,
  MobileHttpsRuntimeProfile,
} from "@/types/mobile-https-runtime";

const MAX_RUNTIME_FILE_BYTES = 64 * 1024;
const FRESHNESS_LIMIT_SECONDS = 20;
const FUTURE_CLOCK_TOLERANCE_SECONDS = 10;
const DEFAULT_PORT = 3443;

interface RuntimePayload {
  schemaVersion: number;
  generatedAt: string;
  hostIp: string | null;
  candidateIps: string[];
  origin: string | null;
  port: number;
  detectionSource: string | null;
  ready: boolean;
  message: string;
  certificate: MobileHttpsRuntimeCertificate;
  https: MobileHttpsRuntimeHealth;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function unavailable(message: string): MobileHttpsRuntimeProfile {
  return {
    available: false,
    state: "UNAVAILABLE",
    ready: false,
    fresh: false,
    generatedAt: null,
    ageSeconds: null,
    hostIp: null,
    candidateIps: [],
    origin: null,
    port: DEFAULT_PORT,
    detectionSource: null,
    certificate: null,
    https: null,
    message,
  };
}

const RUNTIME_FILE = path.join(
  /*turbopackIgnore: true*/ process.cwd(),
  "artifacts",
  "mobile-https-runtime",
  "network-profile.json",
);

async function findRuntimeFile(): Promise<string | null> {
  try {
    const metadata = await lstat(RUNTIME_FILE);
    if (
      metadata.isFile() &&
      !metadata.isSymbolicLink() &&
      metadata.size <= MAX_RUNTIME_FILE_BYTES
    ) {
      return RUNTIME_FILE;
    }
  } catch {
    // Runtime Agent가 아직 profile을 생성하지 않은 상태입니다.
  }

  return null;
}

function readCertificate(
  value: unknown,
): MobileHttpsRuntimeCertificate | null {
  if (!isRecord(value)) {
    return null;
  }

  const sanIps = Array.isArray(value.sanIps)
    ? value.sanIps.filter(
        (item): item is string =>
          typeof item === "string" && isIP(item) === 4,
      )
    : [];

  if (
    typeof value.available !== "boolean" ||
    typeof value.sanMatch !== "boolean" ||
    typeof value.expired !== "boolean" ||
    !(
      value.notAfter === null ||
      typeof value.notAfter === "string"
    )
  ) {
    return null;
  }

  return {
    available: value.available,
    sanMatch: value.sanMatch,
    sanIps,
    notAfter: value.notAfter,
    expired: value.expired,
  };
}

function readHealth(value: unknown): MobileHttpsRuntimeHealth | null {
  if (!isRecord(value)) {
    return null;
  }

  if (
    value.status !== "PASS" &&
    value.status !== "BLOCKED" &&
    value.status !== "FAIL" &&
    value.status !== "UNKNOWN"
  ) {
    return null;
  }

  return {
    status: value.status,
    url: typeof value.url === "string" ? value.url : null,
    httpStatus:
      typeof value.httpStatus === "number" &&
      Number.isInteger(value.httpStatus)
        ? value.httpStatus
        : null,
    error: typeof value.error === "string" ? value.error : null,
  };
}

function parsePayload(value: unknown): RuntimePayload | null {
  if (!isRecord(value) || value.schemaVersion !== 1) {
    return null;
  }

  if (
    typeof value.generatedAt !== "string" ||
    !Number.isFinite(Date.parse(value.generatedAt)) ||
    !Number.isInteger(value.port) ||
    typeof value.port !== "number" ||
    value.port < 1 ||
    value.port > 65_535 ||
    typeof value.ready !== "boolean" ||
    typeof value.message !== "string"
  ) {
    return null;
  }

  const hostIp =
    typeof value.hostIp === "string" && isIP(value.hostIp) === 4
      ? value.hostIp
      : null;
  const candidateIps = Array.isArray(value.candidateIps)
    ? value.candidateIps.filter(
        (item): item is string =>
          typeof item === "string" && isIP(item) === 4,
      )
    : [];
  const origin =
    typeof value.origin === "string" ? value.origin : null;

  if (origin !== null) {
    try {
      const parsed = new URL(origin);
      if (
        parsed.protocol !== "https:" ||
        parsed.username ||
        parsed.password ||
        parsed.pathname !== "/" ||
        parsed.search ||
        parsed.hash ||
        hostIp === null ||
        parsed.hostname !== hostIp ||
        Number(parsed.port || "443") !== value.port
      ) {
        return null;
      }
    } catch {
      return null;
    }
  }

  const certificate = readCertificate(value.certificate);
  const https = readHealth(value.https);
  if (!certificate || !https) {
    return null;
  }

  return {
    schemaVersion: 1,
    generatedAt: value.generatedAt,
    hostIp,
    candidateIps,
    origin,
    port: value.port,
    detectionSource:
      typeof value.detectionSource === "string"
        ? value.detectionSource
        : null,
    ready: value.ready,
    message: value.message,
    certificate,
    https,
  };
}

export async function loadMobileHttpsRuntimeProfile(
  now = new Date(),
): Promise<MobileHttpsRuntimeProfile> {
  const runtimeFile = await findRuntimeFile();
  if (!runtimeFile) {
    return unavailable(
      "Windows host 네트워크 자동 감지 정보가 없습니다. VisionFlow Mobile HTTPS Runtime Agent를 실행하세요.",
    );
  }

  let payload: RuntimePayload | null = null;

  try {
    const bytes = await readFile(runtimeFile);
    payload = parsePayload(
      JSON.parse(
        bytes.toString("utf8").replace(/^\uFEFF/, ""),
      ),
    );
  } catch (error) {
    console.error("Mobile HTTPS runtime profile read error:", error);
  }

  if (!payload) {
    return unavailable(
      "Windows host 네트워크 자동 감지 정보가 올바르지 않습니다.",
    );
  }

  const ageSeconds =
    (now.getTime() - Date.parse(payload.generatedAt)) / 1000;
  const fresh =
    ageSeconds >= -FUTURE_CLOCK_TOLERANCE_SECONDS &&
    ageSeconds <= FRESHNESS_LIMIT_SECONDS;
  const state = !fresh
    ? "STALE"
    : payload.ready
      ? "READY"
      : "BLOCKED";

  return {
    available: true,
    state,
    ready: fresh && payload.ready,
    fresh,
    generatedAt: payload.generatedAt,
    ageSeconds: Math.max(
      0,
      Math.round(ageSeconds * 10) / 10,
    ),
    hostIp: payload.hostIp,
    candidateIps: payload.candidateIps,
    origin: payload.origin,
    port: payload.port,
    detectionSource: payload.detectionSource,
    certificate: payload.certificate,
    https: payload.https,
    message: fresh
      ? payload.message
      : "자동 감지 정보가 오래되었습니다. Runtime Agent가 실행 중인지 확인하세요.",
  };
}
