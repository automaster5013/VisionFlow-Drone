import {
  proxyMaintenanceRequest,
} from "@/lib/server/maintenance-work-order-proxy";

export async function GET() {
  return proxyMaintenanceRequest(
    "/api/maintenance/priorities",
    {
      method: "GET",
      headers: { Accept: "application/json" },
    },
    "정비 우선조치 큐",
  );
}
