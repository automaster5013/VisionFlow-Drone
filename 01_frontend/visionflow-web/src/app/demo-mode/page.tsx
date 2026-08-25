import type { Metadata } from "next";

import { DemoModeConsole } from "@/components/demo/demo-mode-console";
import { OperatorAccessDenied } from "@/components/security/operator-access-denied";
import { requireOperatorPageAccess } from "@/lib/server/protected-page";

export const metadata: Metadata = {
  title: "시연 모드 | VisionFlow",
  description:
    "스마트폰 실시간 촬영과 비상용 로컬 더미영상 AI 추론을 전환합니다.",
};

export const dynamic = "force-dynamic";

export default async function DemoModePage() {
  const allowed = await requireOperatorPageAccess(
    "/demo-mode",
    "OPERATOR",
  );

  if (!allowed) {
    return (
      <OperatorAccessDenied
        title="시연 모드"
        requirement="OPERATOR"
      />
    );
  }

  return (
    <div
      data-demo-mode-command
      className="vf-demo-mode-command min-h-full"
    >
      <div className="mx-auto max-w-[1500px]">
        <DemoModeConsole />
      </div>
    </div>
  );
}