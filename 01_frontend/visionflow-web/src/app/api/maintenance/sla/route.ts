import {
  proxyMaintenanceRequest,
} from "@/lib/server/maintenance-work-order-proxy";

export async function GET() {
  return proxyMaintenanceRequest(
    "/api/maintenance/sla",
    {
      method: "GET",
      headers: { Accept: "application/json" },
    },
    "정비 SLA 자동화 상태",
  );
}
