import {
  badMaintenanceRequest,
  isPositiveMaintenanceId,
  proxyMaintenanceRequest,
} from "@/lib/server/maintenance-work-order-proxy";

interface RouteContext {
  params: Promise<{ id: string }>;
}

export async function GET(_request: Request, context: RouteContext) {
  const { id } = await context.params;
  if (!isPositiveMaintenanceId(id)) {
    return badMaintenanceRequest("잘못된 점검 작업지시 ID입니다.");
  }

  return proxyMaintenanceRequest(
    `/api/maintenance/work-orders/${encodeURIComponent(id)}`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
    },
    "점검 작업지시 상세",
  );
}
