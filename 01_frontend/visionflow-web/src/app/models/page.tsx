import type { Metadata } from "next";

import { AiModelOperationsCenter } from "@/components/models/ai-model-operations-center";
import { requireOperatorAuthentication } from "@/lib/server/protected-page";

export const metadata: Metadata = {
  title: "AI 모델 운영",
};

export const dynamic = "force-dynamic";

export default async function ModelsPage() {
  await requireOperatorAuthentication("/models");

  return <AiModelOperationsCenter />;
}
