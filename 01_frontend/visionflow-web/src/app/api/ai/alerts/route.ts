import { type NextRequest, NextResponse } from "next/server";

import { proxyAiAlertRequest } from "@/lib/server/ai-alert-proxy";

const SEVERITIES = new Set(["INFO", "WARNING", "CRITICAL"]);
const STATUSES = new Set(["OPEN", "ACKNOWLEDGED", "RESOLVED"]);

function badRequest(message: string) {
    return NextResponse.json(
        { message },
        { status: 400, headers: { "Cache-Control": "no-store" } },
    );
}

export async function GET(request: NextRequest) {
    const input = request.nextUrl.searchParams;
    const rawLimit = input.get("limit") ?? "50";

    if (!/^\d+$/.test(rawLimit)) {
        return badRequest("AI 경보 조회 개수는 숫자여야 합니다.");
    }

    const limit = Number(rawLimit);

    if (!Number.isInteger(limit) || limit < 1 || limit > 200) {
        return badRequest("AI 경보 조회 개수는 1~200이어야 합니다.");
    }

    const rawDroneId = input.get("droneId")?.trim() ?? "";

    if (rawDroneId && (!/^\d+$/.test(rawDroneId) || Number(rawDroneId) < 1)) {
        return badRequest("드론 ID는 1 이상의 정수여야 합니다.");
    }

    const sessionId = input.get("sessionId")?.trim() ?? "";

    if (sessionId.length > 36) {
        return badRequest("세션 ID는 36자 이하여야 합니다.");
    }

    const severity = input.get("severity")?.trim().toUpperCase() ?? "";

    if (severity && !SEVERITIES.has(severity)) {
        return badRequest("지원하지 않는 AI 경보 위험도입니다.");
    }

    const status = input.get("status")?.trim().toUpperCase() ?? "";

    if (status && !STATUSES.has(status)) {
        return badRequest("지원하지 않는 AI 경보 상태입니다.");
    }

    const from = input.get("from")?.trim() ?? "";
    const to = input.get("to")?.trim() ?? "";

    if (from && !Number.isFinite(Date.parse(from))) {
        return badRequest("AI 경보 조회 시작 시각이 올바르지 않습니다.");
    }

    if (to && !Number.isFinite(Date.parse(to))) {
        return badRequest("AI 경보 조회 종료 시각이 올바르지 않습니다.");
    }

    if (from && to && Date.parse(from) > Date.parse(to)) {
        return badRequest("조회 시작 시각은 종료 시각보다 늦을 수 없습니다.");
    }

    const backendSearchParams = new URLSearchParams({ limit: String(limit) });

    if (rawDroneId) {
        backendSearchParams.set("droneId", rawDroneId);
    }

    if (sessionId) {
        backendSearchParams.set("sessionId", sessionId);
    }

    if (severity) {
        backendSearchParams.set("severity", severity);
    }

    if (status) {
        backendSearchParams.set("status", status);
    }

    if (from) {
        backendSearchParams.set("from", from);
    }

    if (to) {
        backendSearchParams.set("to", to);
    }

    return proxyAiAlertRequest(
        `/api/ai/alerts?${backendSearchParams.toString()}`,
        {
            method: "GET",
            headers: { Accept: "application/json" },
        },
        "AI 경보 목록",
    );
}
