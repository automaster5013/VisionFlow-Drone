import { type NextRequest } from "next/server";

import {
  badMaintenanceRequest,
  isPositiveMaintenanceId,
  proxyMaintenanceRequest,
} from "@/lib/server/maintenance-work-order-proxy";
import { rejectCrossOriginOperatorMutation } from "@/lib/server/operator-mutation-guard";

interface RouteContext {
  params: Promise<{ id: string }>;
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  const rejected = rejectCrossOriginOperatorMutation(request);
  if (rejected) return rejected;

  const { id } = await context.params;
  if (!isPositiveMaintenanceId(id)) {
    return badMaintenanceRequest("잘못된 점검 작업지시 ID입니다.");
  }

  return proxyMaintenanceRequest(
    `/api/maintenance/work-orders/${encodeURIComponent(id)}/complete`,
    {
      method: "PATCH",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: await request.text(),
    },
    "기체 점검 완료",
  );
}
