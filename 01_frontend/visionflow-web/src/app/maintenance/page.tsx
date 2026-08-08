import type { Metadata } from "next";

import { MaintenanceWorkOrderBoard } from "@/components/maintenance/maintenance-work-order-board";
import {
  buildProtectedReturnTo,
  requireOperatorAuthentication,
} from "@/lib/server/protected-page";
import type { MaintenanceWorkOrderStatus } from "@/types/maintenance-work-order";

export const metadata: Metadata = {
  title: "기체 점검 작업지시",
};

export const dynamic = "force-dynamic";

type SearchValue = string | string[] | undefined;

interface MaintenancePageProps {
  searchParams: Promise<Record<string, SearchValue>>;
}

function firstSearchValue(value: SearchValue): string {
  return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
}

function positiveInteger(value: string): number | null {
  return /^\d+$/.test(value) && Number(value) > 0
    ? Number(value)
    : null;
}

function workOrderStatus(value: string): MaintenanceWorkOrderStatus | null {
  return value === "OPEN" ||
    value === "IN_PROGRESS" ||
    value === "COMPLETED" ||
    value === "GROUNDED"
    ? value
    : null;
}

export default async function MaintenancePage({
  searchParams,
}: MaintenancePageProps) {
  const query = await searchParams;
  await requireOperatorAuthentication(
    buildProtectedReturnTo("/maintenance", query),
  );
  const initialDroneId = positiveInteger(
    firstSearchValue(query.droneId),
  );
  const initialWorkOrderId = positiveInteger(
    firstSearchValue(query.workOrderId),
  );
  const initialStatus = workOrderStatus(
    firstSearchValue(query.status).toUpperCase(),
  );

  return (
    <MaintenanceWorkOrderBoard
      key={[
        initialDroneId ?? "all",
        initialWorkOrderId ?? "none",
        initialStatus ?? "all",
      ].join(":")}
      initialDroneId={initialDroneId}
      initialWorkOrderId={initialWorkOrderId}
      initialStatus={initialStatus}
    />
  );
}
