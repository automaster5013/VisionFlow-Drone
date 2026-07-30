import type { Metadata } from "next";

import { FleetReliabilityDashboard } from "@/components/dashboard/fleet-reliability-dashboard";

export const metadata: Metadata = {
  title: "기체별 운영 신뢰도 | VisionFlow",
};

export const dynamic = "force-dynamic";

export default function FleetReliabilityPage() {
  return <FleetReliabilityDashboard />;
}
