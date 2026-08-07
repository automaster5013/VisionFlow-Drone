import type { Metadata } from "next";

import { AiModelOperationsCenter } from "@/components/models/ai-model-operations-center";

export const metadata: Metadata = {
  title: "AI 모델 운영",
};

export const dynamic = "force-dynamic";

export default function ModelsPage() {
  return <AiModelOperationsCenter />;
}
