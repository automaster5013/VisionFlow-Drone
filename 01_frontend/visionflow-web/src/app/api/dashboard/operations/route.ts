import { type NextRequest, NextResponse } from "next/server";

import { withBackendOperatorAuth } from "@/lib/server/operator-auth";

const BACKEND_API_URL = (
    process.env.SPRING_API_URL ??
    process.env.BACKEND_API_URL ??
    process.env.API_BASE_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    "http://localhost:8080"
).replace(/\/$/, "");

const SESSION_STATUSES = new Set([
    "READY",
    "ACTIVE",
    "COMPLETED",
    "ABORTED",
]);

function badRequest(message: string) {
    return NextResponse.json(
        { message },
        { status: 400, headers: { "Cache-Control": "no-store" } },
    );
}

export async function GET(request: NextRequest) {
    const input = request.nextUrl.searchParams;
    const rawLimit = input.get("limit") ?? "5";

    if (!/^\d+$/.test(rawLimit)) {
        return badRequest("최근 항목 제한값은 숫자여야 합니다.");
    }

    const limit = Number(rawLimit);

    if (!Number.isInteger(limit) || limit < 1 || limit > 20) {
        return badRequest("최근 항목 제한값은 1~20이어야 합니다.");
    }

    const rawDroneId = input.get("droneId")?.trim() ?? "";

    if (rawDroneId && (!/^\d+$/.test(rawDroneId) || Number(rawDroneId) < 1)) {
        return badRequest("드론 ID는 1 이상의 정수여야 합니다.");
    }

    const status = input.get("status")?.trim().toUpperCase() ?? "";

    if (status && !SESSION_STATUSES.has(status)) {
        return badRequest("지원하지 않는 비행 세션 상태입니다.");
    }

    const from = input.get("from")?.trim() ?? "";
    const to = input.get("to")?.trim() ?? "";

    if (from && !Number.isFinite(Date.parse(from))) {
        return badRequest("조회 시작 시각이 올바르지 않습니다.");
    }

    if (to && !Number.isFinite(Date.parse(to))) {
        return badRequest("조회 종료 시각이 올바르지 않습니다.");
    }

    if (from && to && Date.parse(from) > Date.parse(to)) {
        return badRequest("조회 시작 시각은 종료 시각보다 늦을 수 없습니다.");
    }

    const backendSearchParams = new URLSearchParams({ limit: String(limit) });

    if (rawDroneId) {
        backendSearchParams.set("droneId", rawDroneId);
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

    try {
        const response = await fetch(
            `${BACKEND_API_URL}/api/dashboard/operations?${backendSearchParams}`,
            await withBackendOperatorAuth({
                method: "GET",
                headers: { Accept: "application/json" },
                cache: "no-store",
                signal: AbortSignal.timeout(10_000),
            }),
        );
        const responseBody = await response.text();

        return new NextResponse(responseBody, {
            status: response.status,
            headers: {
                "Content-Type":
                    response.headers.get("content-type") ?? "application/json",
                "Cache-Control": "no-store",
            },
        });
    } catch (error) {
        console.error("운영 대시보드 프록시 오류:", error);

        return NextResponse.json(
            { message: "백엔드 운영 대시보드 API에 연결할 수 없습니다." },
            { status: 502, headers: { "Cache-Control": "no-store" } },
        );
    }
}
