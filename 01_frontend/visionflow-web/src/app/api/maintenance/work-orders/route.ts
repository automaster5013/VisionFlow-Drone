import { type NextRequest } from "next/server";

import {
  badMaintenanceRequest,
  proxyMaintenanceRequest,
} from "@/lib/server/maintenance-work-order-proxy";

const STATUSES = new Set([
  "OPEN",
  "IN_PROGRESS",
  "COMPLETED",
  "GROUNDED",
]);

export async function GET(request: NextRequest) {
  const input = request.nextUrl.searchParams;
  const rawLimit = input.get("limit") ?? "100";

  if (!/^\d+$/.test(rawLimit)) {
    return badMaintenanceRequest("조회 개수는 숫자여야 합니다.");
  }
  const limit = Number(rawLimit);
  if (!Number.isInteger(limit) || limit < 1 || limit > 500) {
    return badMaintenanceRequest("조회 개수는 1~500이어야 합니다.");
  }

  const droneId = input.get("droneId")?.trim() ?? "";
  if (droneId && (!/^\d+$/.test(droneId) || Number(droneId) < 1)) {
    return badMaintenanceRequest("드론 ID는 1 이상의 정수여야 합니다.");
  }

  const status = input.get("status")?.trim().toUpperCase() ?? "";
  if (status && !STATUSES.has(status)) {
    return badMaintenanceRequest("지원하지 않는 작업지시 상태입니다.");
  }

  const query = new URLSearchParams({ limit: String(limit) });
  if (droneId) query.set("droneId", droneId);
  if (status) query.set("status", status);

  return proxyMaintenanceRequest(
    `/api/maintenance/work-orders?${query}`,
    { method: "GET", headers: { Accept: "application/json" } },
    "점검 작업지시 목록",
  );
}
