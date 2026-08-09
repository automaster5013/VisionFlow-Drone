import { notFound } from "next/navigation";

import { IncidentReportView } from "@/components/incidents/incident-report-view";
import { OperatorAccessDenied } from "@/components/security/operator-access-denied";
import { requireOperatorPageAccess } from "@/lib/server/protected-page";

interface IncidentReportPageProps {
  params: Promise<{ id: string }>;
}

export const dynamic = "force-dynamic";

export default async function IncidentReportPage({
  params,
}: IncidentReportPageProps) {
  const { id } = await params;

  if (!/^\d+$/.test(id) || Number(id) < 1) {
    notFound();
  }

  const allowed = await requireOperatorPageAccess(
    `/incidents/${id}/report`,
    "AUTHENTICATED",
  );

  if (!allowed) {
    return (
      <OperatorAccessDenied
        title="Incident 보고서"
        requirement="AUTHENTICATED"
      />
    );
  }

  return <IncidentReportView incidentId={Number(id)} />;
}
