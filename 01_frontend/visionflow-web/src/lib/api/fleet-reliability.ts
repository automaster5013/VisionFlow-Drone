import {
  extractFleetReliabilityResponse,
  type FleetReliabilityResponse,
} from "@/types/fleet-reliability";

const DEFAULT_API_URL = "http://localhost:8080";

function getApiBaseUrl(): string {
  return (
    process.env.SPRING_API_URL ??
    process.env.BACKEND_API_URL ??
    process.env.API_BASE_URL ??
    DEFAULT_API_URL
  ).replace(/\/$/, "");
}

export async function getFleetReliability(
  limitPerDrone = 20,
): Promise<FleetReliabilityResponse> {
  if (
    !Number.isInteger(limitPerDrone) ||
    limitPerDrone < 1 ||
    limitPerDrone > 100
  ) {
    throw new Error("기체별 품질 평가 제한값은 1~100이어야 합니다.");
  }

  const query = new URLSearchParams({
    limitPerDrone: String(limitPerDrone),
  });
  let response: Response;

  try {
    response = await fetch(
      `${getApiBaseUrl()}/api/flight-quality/fleet-reliability?${query}`,
      {
        method: "GET",
        headers: { Accept: "application/json" },
        cache: "no-store",
        signal: AbortSignal.timeout(5_000),
      },
    );
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown connection error";

    throw new Error(`함대 운영 신뢰도 API 연결에 실패했습니다: ${message}`);
  }

  if (!response.ok) {
    throw new Error(
      `함대 운영 신뢰도 API 호출 실패: HTTP ${response.status} ${response.statusText}`,
    );
  }

  let body: unknown;

  try {
    body = await response.json();
  } catch {
    throw new Error("함대 운영 신뢰도 응답을 JSON으로 변환할 수 없습니다.");
  }

  const data = extractFleetReliabilityResponse(body);

  if (!data) {
    throw new Error("함대 운영 신뢰도 API 응답 형식이 올바르지 않습니다.");
  }

  return data;
}
