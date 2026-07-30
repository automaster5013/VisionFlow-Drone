import "server-only";

import { NextResponse } from "next/server";

import { withBackendOperatorAuth } from "@/lib/server/operator-auth";

const BACKEND_API_URL = (
    process.env.SPRING_API_URL ??
    process.env.BACKEND_API_URL ??
    process.env.API_BASE_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    "http://localhost:8080"
).replace(/\/$/, "");

export function badAuditRequest(message: string) {
    return NextResponse.json(
        { message },
        { status: 400, headers: { "Cache-Control": "no-store" } },
    );
}

export async function proxyAuditRequest(backendPath: string) {
    try {
        const response = await fetch(`${BACKEND_API_URL}${backendPath}`, await withBackendOperatorAuth({
            method: "GET",
            headers: { Accept: "application/json" },
            cache: "no-store",
            signal: AbortSignal.timeout(10_000),
        }));
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
        console.error("감사 로그 프록시 오류:", error);
        return NextResponse.json(
            { message: "백엔드 감사 로그 API에 연결할 수 없습니다." },
            { status: 502, headers: { "Cache-Control": "no-store" } },
        );
    }
}

export async function proxyAuditDownload(backendPath: string) {
    try {
        const response = await fetch(`${BACKEND_API_URL}${backendPath}`, await withBackendOperatorAuth({
            method: "GET",
            headers: { Accept: "text/csv, application/json" },
            cache: "no-store",
            signal: AbortSignal.timeout(30_000),
        }));
        const responseBody = await response.arrayBuffer();
        const headers = new Headers({
            "Content-Type":
                response.headers.get("content-type") ??
                "application/octet-stream",
            "Cache-Control": "no-store",
        });
        for (const headerName of [
            "content-disposition",
            "x-visionflow-exported-count",
            "x-visionflow-total-count",
        ]) {
            const value = response.headers.get(headerName);
            if (value) headers.set(headerName, value);
        }
        return new NextResponse(responseBody, {
            status: response.status,
            headers,
        });
    } catch (error) {
        console.error("감사 로그 CSV 프록시 오류:", error);
        return NextResponse.json(
            { message: "백엔드 감사 로그 CSV API에 연결할 수 없습니다." },
            { status: 502, headers: { "Cache-Control": "no-store" } },
        );
    }
}

export async function proxyAuditMutationRequest(
    backendPath: string,
    request: Request,
) {
    try {
        const headers = new Headers({ Accept: "application/json" });
        for (const headerName of ["x-request-id"]) {
            const value = request.headers.get(headerName);
            if (value) headers.set(headerName, value);
        }
        const response = await fetch(`${BACKEND_API_URL}${backendPath}`, await withBackendOperatorAuth({
            method: "POST",
            headers,
            cache: "no-store",
            signal: AbortSignal.timeout(30_000),
        }));
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
        console.error("감사 로그 보존 정리 프록시 오류:", error);
        return NextResponse.json(
            { message: "백엔드 감사 로그 보존 API에 연결할 수 없습니다." },
            { status: 502, headers: { "Cache-Control": "no-store" } },
        );
    }
}
