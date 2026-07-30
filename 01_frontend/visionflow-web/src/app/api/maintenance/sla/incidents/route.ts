import {
  proxyMaintenanceRequest,
} from "@/lib/server/maintenance-work-order-proxy";

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  const windowDays = requestUrl.searchParams.get("windowDays") ?? "30";

  return proxyMaintenanceRequest(
    `/api/maintenance/sla/incidents?windowDays=${encodeURIComponent(windowDays)}`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
    },
    "정비 SLA Incident 추적",
  );
}
