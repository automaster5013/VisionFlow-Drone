import { NextResponse } from "next/server";

import { withAiInternalAuth } from "@/lib/server/ai-internal-auth";
import { getOperatorSecurityStatus } from "@/lib/server/operator-security";

const AI_STREAM_API_URL = (
  process.env.AI_STREAM_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function sanitizeClass(value: unknown): { id: number; name: string } | null {
  if (!isRecord(value)) return null;
  const id = finiteNumber(value.id);
  const name = nullableString(value.name);
  return id !== null && Number.isInteger(id) && name !== null ? { id, name } : null;
}

function sanitizeModelStatus(value: unknown): Record<string, unknown> | null {
  if (!isRecord(value)) return null;

  const classes = Array.isArray(value.classes)
    ? value.classes.map(sanitizeClass).filter((item) => item !== null)
    : [];
  const capability = Array.isArray(value.cudaCapability)
    ? value.cudaCapability.map(finiteNumber).filter((item) => item !== null)
    : [];

  return {
    profile: nullableString(value.profile),
    localFile: value.localFile === true,
    sizeBytes: finiteNumber(value.sizeBytes),
    sha256: nullableString(value.sha256),
    classCount: finiteNumber(value.classCount),
    classes,
    confidence: finiteNumber(value.confidence),
    iou: finiteNumber(value.iou),
    imageSize: finiteNumber(value.imageSize),
    deviceRequested: nullableString(value.deviceRequested),
    deviceEffective: nullableString(value.deviceEffective),
    requireCuda: value.requireCuda === true,
    torchVersion: nullableString(value.torchVersion),
    torchCudaVersion: nullableString(value.torchCudaVersion),
    cudnnVersion: finiteNumber(value.cudnnVersion),
    cudaAvailable: value.cudaAvailable === true,
    cudaDeviceCount: finiteNumber(value.cudaDeviceCount),
    cudaDeviceIndex: finiteNumber(value.cudaDeviceIndex),
    cudaDeviceName: nullableString(value.cudaDeviceName),
    cudaCapability: capability,
    cudaTotalMemoryBytes: finiteNumber(value.cudaTotalMemoryBytes),
  };
}

export async function GET() {
  const operator = await getOperatorSecurityStatus();

  if (!operator) {
    return NextResponse.json(
      { message: "운영자 권한 상태를 확인할 수 없습니다." },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }

  if (operator.enabled && !operator.authenticated) {
    return NextResponse.json(
      { message: "AI 모델 운영 상태를 보려면 운영자 로그인이 필요합니다." },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
  }

  try {
    const response = await fetch(
      `${AI_STREAM_API_URL}/api/models/status`,
      withAiInternalAuth({
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
        signal: AbortSignal.timeout(2_000),
      }),
    );
    const body: unknown = await response.json().catch(() => null);

    if (!response.ok) {
      return NextResponse.json(
        isRecord(body) ? body : { message: "AI 모델 상태 조회에 실패했습니다." },
        { status: response.status, headers: { "Cache-Control": "no-store" } },
      );
    }

    const sanitized = sanitizeModelStatus(body);
    if (!sanitized) {
      return NextResponse.json(
        { message: "AI 모델 상태 응답 형식이 올바르지 않습니다." },
        { status: 502, headers: { "Cache-Control": "no-store" } },
      );
    }

    return NextResponse.json(sanitized, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (error) {
    console.error("AI 모델 상태 프록시 오류:", error);
    return NextResponse.json(
      { message: "AI 모델 상태 서버에 연결할 수 없습니다." },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
