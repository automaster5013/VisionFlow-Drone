import { notFound } from "next/navigation";

import { IncidentReportView } from "@/components/incidents/incident-report-view";

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

    return <IncidentReportView incidentId={Number(id)} />;
}
