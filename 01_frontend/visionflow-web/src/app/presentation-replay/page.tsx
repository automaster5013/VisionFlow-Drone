import { PresentationReplayConsole } from "@/components/demo/presentation-replay-console";
import { OperatorAccessDenied } from "@/components/security/operator-access-denied";
import { requireOperatorPageAccess } from "@/lib/server/protected-page";
export const dynamic = "force-dynamic";
export const metadata = { title: "발표 통합 시연 | VisionFlow" };
export default async function PresentationReplayPage() {
  if (!await requireOperatorPageAccess("/presentation-replay", "OPERATOR")) return <OperatorAccessDenied title="발표 통합 시연" requirement="OPERATOR" />;
  return <PresentationReplayConsole />;
}
