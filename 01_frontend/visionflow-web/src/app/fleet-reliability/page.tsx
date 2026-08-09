import type { Metadata } from "next";

import { FleetReliabilityDashboard } from "@/components/dashboard/fleet-reliability-dashboard";
import { OperatorAccessDenied } from "@/components/security/operator-access-denied";
import { requireOperatorPageAccess } from "@/lib/server/protected-page";

export const metadata: Metadata = {
  title: "기체별 운영 신뢰도 | VisionFlow",
};

export const dynamic = "force-dynamic";

export default async function FleetReliabilityPage() {
  const allowed = await requireOperatorPageAccess(
    "/fleet-reliability",
    "AUTHENTICATED",
  );

  if (!allowed) {
    return (
      <OperatorAccessDenied
        title="기체별 운영 신뢰도"
        requirement="AUTHENTICATED"
      />
    );
  }

  return <FleetReliabilityDashboard />;
}
