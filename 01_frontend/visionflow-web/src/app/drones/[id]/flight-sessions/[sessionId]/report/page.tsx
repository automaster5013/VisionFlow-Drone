import { notFound } from "next/navigation";

import { FlightSessionReportView } from "@/components/drones/flight-session-report-view";
import { OperatorAccessDenied } from "@/components/security/operator-access-denied";
import { requireOperatorPageAccess } from "@/lib/server/protected-page";

interface FlightSessionReportPageProps {
  params: Promise<{
    id: string;
    sessionId: string;
  }>;
}

export const dynamic = "force-dynamic";

export default async function FlightSessionReportPage({
  params,
}: FlightSessionReportPageProps) {
  const { id, sessionId: rawSessionId } = await params;
  const sessionId = rawSessionId.trim();

  if (
    !/^\d+$/.test(id) ||
    Number(id) < 1 ||
    sessionId.length < 1 ||
    sessionId.length > 36
  ) {
    notFound();
  }

  const returnTo =
    `/drones/${id}/flight-sessions/` +
    `${encodeURIComponent(sessionId)}/report`;
  const allowed = await requireOperatorPageAccess(
    returnTo,
    "AUTHENTICATED",
  );

  if (!allowed) {
    return (
      <OperatorAccessDenied
        title="비행 세션 보고서"
        requirement="AUTHENTICATED"
      />
    );
  }

  return (
    <FlightSessionReportView droneId={Number(id)} sessionId={sessionId} />
  );
}
