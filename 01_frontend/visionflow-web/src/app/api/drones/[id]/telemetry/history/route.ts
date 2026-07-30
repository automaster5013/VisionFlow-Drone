import {
    type NextRequest,
    NextResponse,
} from "next/server";

const SPRING_API_URL =
    process.env.SPRING_API_URL ??
    "http://localhost:8080";

interface RouteContext {
    params: Promise<{
        id: string;
    }>;
}

export async function GET(
    request: NextRequest,
    context: RouteContext,
) {
    const { id } = await context.params;

    const query = new URLSearchParams();

    for (const name of ["from", "to", "limit"]) {
        const value =
            request.nextUrl.searchParams.get(name);

        if (value) {
            query.set(name, value);
        }
    }

    const queryString = query.toString();

    const backendUrl =
        `${SPRING_API_URL}/api/drones/` +
        `${encodeURIComponent(id)}/telemetry/history` +
        (queryString ? `?${queryString}` : "");

    try {
        const response = await fetch(backendUrl, {
            method: "GET",
            headers: {
                Accept: "application/json",
            },
            cache: "no-store",
        });

        const body = await response.text();

        return new NextResponse(
            body.length > 0 ? body : null,
            {
                status: response.status,
                headers: {
                    "Content-Type":
                        response.headers.get(
                            "content-type",
                        ) ?? "application/json",
                },
            },
        );
    } catch (error) {
        console.error(
            "과거 텔레메트리 프록시 오류:",
            error,
        );

        return NextResponse.json(
            {
                code: "BACKEND_CONNECTION_ERROR",
                message:
                    "백엔드 서버에 연결할 수 없습니다.",
            },
            {
                status: 503,
            },
        );
    }
}