import { MobileDroneControl } from "@/components/mobile/mobile-drone-control";
import { OperatorAccessDenied } from "@/components/security/operator-access-denied";
import { requireOperatorPageAccess } from "@/lib/server/protected-page";

export const dynamic = "force-dynamic";

export default async function MobileControlPage() {
  const allowed = await requireOperatorPageAccess(
    "/mobile-control",
    "OPERATOR",
  );

  if (!allowed) {
    return (
      <OperatorAccessDenied
        title="스마트폰 가상 드론 송신기"
        requirement="OPERATOR"
      />
    );
  }

  return <MobileDroneControl />;
}
