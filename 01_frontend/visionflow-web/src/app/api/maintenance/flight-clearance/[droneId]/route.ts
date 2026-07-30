import {
  badMaintenanceRequest,
  isPositiveMaintenanceId,
  proxyMaintenanceRequest,
} from "@/lib/server/maintenance-work-order-proxy";

interface RouteContext {
  params: Promise<{ droneId: string }>;
}

export async function GET(_request: Request, context: RouteContext) {
  const { droneId } = await context.params;
  if (!isPositiveMaintenanceId(droneId)) {
    return badMaintenanceRequest("잘못된 드론 ID입니다.");
  }

  return proxyMaintenanceRequest(
    `/api/maintenance/flight-clearance/${encodeURIComponent(droneId)}`,
    { method: "GET", headers: { Accept: "application/json" } },
    "기체 비행 허가 상태",
  );
}
