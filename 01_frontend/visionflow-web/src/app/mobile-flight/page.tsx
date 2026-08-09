import { MobileFlightControl } from "@/components/mobile/mobile-flight-control";
import { OperatorAccessDenied } from "@/components/security/operator-access-denied";
import { requireOperatorPageAccess } from "@/lib/server/protected-page";

export const dynamic = "force-dynamic";

export default async function MobileFlightPage() {
  const allowed = await requireOperatorPageAccess(
    "/mobile-flight",
    "OPERATOR",
  );

  if (!allowed) {
    return (
      <OperatorAccessDenied
        title="스마트폰 가상 드론 비행"
        requirement="OPERATOR"
      />
    );
  }

  return <MobileFlightControl />;
}
