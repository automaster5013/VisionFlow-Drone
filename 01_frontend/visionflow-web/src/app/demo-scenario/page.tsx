import type { Metadata } from "next";

import { DemoScenarioConsole } from "@/components/demo/demo-scenario-console";
import { OperatorAccessDenied } from "@/components/security/operator-access-denied";
import { requireOperatorPageAccess } from "@/lib/server/protected-page";

export const metadata: Metadata = {
  title: "발표 시연 콘솔 | VisionFlow",
};

export const dynamic = "force-dynamic";

export default async function DemoScenarioPage() {
  const allowed = await requireOperatorPageAccess(
    "/demo-scenario",
    "OPERATOR",
  );

  if (!allowed) {
    return (
      <OperatorAccessDenied
        title="발표 시연 콘솔"
        requirement="OPERATOR"
      />
    );
  }

  return <DemoScenarioConsole />;
}