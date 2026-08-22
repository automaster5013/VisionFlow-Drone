import type { Metadata } from "next";

import { EventOperationsCenter } from "@/components/events/event-operations-center";
import { requireOperatorAuthentication } from "@/lib/server/protected-page";
import { requireOperatorPageAccess } from "@/lib/server/protected-page";

export const metadata: Metadata = {
  title: "통합 이벤트 관제",
};

export const dynamic = "force-dynamic";

export default async function EventsPage() {
  await requireOperatorAuthentication("/events");
  const canManageSnapshots = await requireOperatorPageAccess(
    "/events",
    "OPERATOR",
  );

  if (!canManageSnapshots) {
    return <EventOperationsCenter />;
  }

  return (
    <EventOperationsCenter
      canManageSnapshots={canManageSnapshots}
    />
  );
}
