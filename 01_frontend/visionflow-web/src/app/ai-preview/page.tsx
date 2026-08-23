import type { Metadata } from "next";

import { MobileAiInferencePreview } from "@/components/mobile/mobile-ai-inference-preview";
import { OperatorAccessDenied } from "@/components/security/operator-access-denied";
import { requireOperatorPageAccess } from "@/lib/server/protected-page";

export const metadata: Metadata = {
  title: "AI 실시간 추론",
  description: "VisionFlow YOLO 실시간 분석 영상을 독립 창에서 확인합니다.",
};

export default async function AiPreviewPage() {
  const allowed = await requireOperatorPageAccess(
    "/ai-preview",
    "AUTHENTICATED",
  );

  if (!allowed) {
    return (
      <OperatorAccessDenied
        title="AI 실시간 추론"
        requirement="AUTHENTICATED"
      />
    );
  }

  return (
    <main className="vf-camera-preview-page min-h-screen p-4 text-slate-900 sm:p-6">
      <div className="mx-auto max-w-6xl">
        <MobileAiInferencePreview allowPopout={false} />
      </div>
    </main>
  );
}
