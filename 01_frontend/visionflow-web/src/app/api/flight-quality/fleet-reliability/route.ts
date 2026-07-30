import { type NextRequest, NextResponse } from "next/server";

const BACKEND_API_URL = (
  process.env.BACKEND_API_URL ??
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8080"
).replace(/\/$/, "");

function badRequest(message: string) {
  return NextResponse.json(
    { message },
    {
      status: 400,
      headers: { "Cache-Control": "no-store" },
    },
  );
}

export async function GET(request: NextRequest) {
  const rawLimit =
    request.nextUrl.searchParams.get("limitPerDrone") ?? "20";

  if (!/^\d+$/.test(rawLimit)) {
    return badRequest("기체별 품질 평가 제한값은 1~100이어야 합니다.");
  }

  const limitPerDrone = Number(rawLimit);
  if (
    !Number.isInteger(limitPerDrone) ||
    limitPerDrone < 1 ||
    limitPerDrone > 100
  ) {
    return badRequest("기체별 품질 평가 제한값은 1~100이어야 합니다.");
  }

  try {
    const query = new URLSearchParams({
      limitPerDrone: String(limitPerDrone),
    });
    const response = await fetch(
      `${BACKEND_API_URL}/api/flight-quality/fleet-reliability?${query}`,
      {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
        signal: AbortSignal.timeout(15_000),
      },
    );
    const body = await response.text();

    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    console.error("함대 운영 신뢰도 프록시 오류:", error);

    return NextResponse.json(
      { message: "백엔드 함대 운영 신뢰도 API에 연결할 수 없습니다." },
      {
        status: 502,
        headers: { "Cache-Control": "no-store" },
      },
    );
  }
}
