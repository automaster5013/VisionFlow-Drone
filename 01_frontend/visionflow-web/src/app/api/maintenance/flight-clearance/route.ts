import {
  proxyMaintenanceRequest,
} from "@/lib/server/maintenance-work-order-proxy";

export async function GET() {
  return proxyMaintenanceRequest(
    "/api/maintenance/flight-clearance",
    {
      method: "GET",
      headers: { Accept: "application/json" },
    },
    "함대 비행 허가 상태",
  );
}
