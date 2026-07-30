import { type NextRequest } from "next/server";

import {
  badMaintenanceRequest,
  proxyMaintenanceRequest,
} from "@/lib/server/maintenance-work-order-proxy";

export async function GET(request: NextRequest) {
  const rawWindowDays =
    request.nextUrl.searchParams.get("windowDays") ?? "30";

  if (!/^\d+$/.test(rawWindowDays)) {
    return badMaintenanceRequest("조회 기간은 숫자여야 합니다.");
  }
  const windowDays = Number(rawWindowDays);
  if (
    !Number.isInteger(windowDays) ||
    windowDays < 1 ||
    windowDays > 365
  ) {
    return badMaintenanceRequest("조회 기간은 1~365일이어야 합니다.");
  }

  return proxyMaintenanceRequest(
    `/api/maintenance/metrics?windowDays=${windowDays}`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
    },
    "정비 운영 KPI",
  );
}
