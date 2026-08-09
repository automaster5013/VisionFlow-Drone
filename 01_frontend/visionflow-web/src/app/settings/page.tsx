import type { Metadata } from "next";

import { OperatorAccessDenied } from "@/components/security/operator-access-denied";
import { OperatorConsoleSettingsCenter } from "@/components/settings/operator-console-settings-center";
import { requireOperatorPageAccess } from "@/lib/server/protected-page";

export const metadata: Metadata = {
  title: "운영 설정",
};

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const allowed = await requireOperatorPageAccess(
    "/settings",
    "AUTHENTICATED",
  );

  if (!allowed) {
    return (
      <OperatorAccessDenied
        title="운영 설정 센터"
        requirement="AUTHENTICATED"
      />
    );
  }

  return <OperatorConsoleSettingsCenter />;
}
