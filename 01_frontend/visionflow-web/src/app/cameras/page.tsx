import { redirect } from "next/navigation";

import { OperatorAccessDenied } from "@/components/security/operator-access-denied";
import { requireOperatorPageAccess } from "@/lib/server/protected-page";

export default async function CamerasCompatibilityPage() {
  const allowed = await requireOperatorPageAccess(
    "/cameras",
    "OPERATOR",
  );

  if (!allowed) {
    return (
      <OperatorAccessDenied
        title="카메라 운영"
        requirement="OPERATOR"
      />
    );
  }

  redirect("/mobile-camera");
}
