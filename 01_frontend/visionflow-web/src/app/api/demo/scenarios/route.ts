import { type NextRequest } from "next/server";

import {
    badDemoRequest,
    proxyDemoScenarioRequest,
} from "@/lib/server/demo-scenario-proxy";
import { rejectCrossOriginOperatorMutation } from "@/lib/server/operator-mutation-guard";

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}

export async function POST(request: NextRequest) {
    const rejected = rejectCrossOriginOperatorMutation(request);
    if (rejected) {
        return rejected;
    }

    let body: unknown;
    try {
        body = await request.json();
    } catch {
        return badDemoRequest("요청 본문은 올바른 JSON이어야 합니다.");
    }

    if (!isRecord(body)) {
        return badDemoRequest("시연 시작 요청 형식이 올바르지 않습니다.");
    }

    const droneId = body.droneId;
    const latitude = body.latitude;
    const longitude = body.longitude;
    if (
        typeof droneId !== "number" ||
        !Number.isInteger(droneId) ||
        droneId < 1
    ) {
        return badDemoRequest("드론 ID는 1 이상의 정수여야 합니다.");
    }
    if (
        typeof latitude !== "number" ||
        !Number.isFinite(latitude) ||
        latitude < -90 ||
        latitude > 90
    ) {
        return badDemoRequest("위도는 -90~90 범위여야 합니다.");
    }
    if (
        typeof longitude !== "number" ||
        !Number.isFinite(longitude) ||
        longitude < -180 ||
        longitude > 180
    ) {
        return badDemoRequest("경도는 -180~180 범위여야 합니다.");
    }

    return proxyDemoScenarioRequest(
        "/api/demo/scenarios",
        {
            method: "POST",
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ droneId, latitude, longitude }),
        },
        "시연 시나리오 시작",
    );
}
