import { notFound } from "next/navigation";

import { FlightSessionReportView } from "@/components/drones/flight-session-report-view";

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

  return (
    <FlightSessionReportView droneId={Number(id)} sessionId={sessionId} />
  );
}
