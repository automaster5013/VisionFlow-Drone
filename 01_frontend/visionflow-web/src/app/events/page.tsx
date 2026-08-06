import type { Metadata } from "next";

import { EventOperationsCenter } from "@/components/events/event-operations-center";

export const metadata: Metadata = {
  title: "통합 이벤트 관제",
};

export const dynamic = "force-dynamic";

export default function EventsPage() {
  return <EventOperationsCenter />;
}
