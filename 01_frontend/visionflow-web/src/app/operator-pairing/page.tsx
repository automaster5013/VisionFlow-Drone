import type { Metadata } from "next";

import { OperatorPairingConsole } from "@/components/security/operator-pairing-console";
import { OperatorAccessDenied } from "@/components/security/operator-access-denied";
import { requireOperatorPageAccess } from "@/lib/server/protected-page";

export const metadata: Metadata = {
  title: "모바일 QR 로그인",
};

export const dynamic = "force-dynamic";

export default async function OperatorPairingPage() {
  const allowed = await requireOperatorPageAccess(
    "/operator-pairing",
    "AUTHENTICATED",
  );

  if (!allowed) {
    return (
      <OperatorAccessDenied
        title="모바일 QR 로그인"
        requirement="AUTHENTICATED"
      />
    );
  }

  return <OperatorPairingConsole />;
}
