import type { Metadata } from "next";

import { MobileCameraStreamer } from "@/components/mobile/mobile-camera-streamer";
import { OperatorAccessDenied } from "@/components/security/operator-access-denied";
import { requireOperatorPageAccess } from "@/lib/server/protected-page";

export const metadata: Metadata = {
  title: "노트북 AI 카메라",
  description: "노트북 웹캠 영상을 VisionFlow AI 서버로 전송하고 분석 상태를 확인합니다.",
};

export default async function MobileCameraPage() {
  const allowed = await requireOperatorPageAccess(
    "/mobile-camera",
    "OPERATOR",
  );

  if (!allowed) {
    return (
      <OperatorAccessDenied
        title="노트북 AI 카메라"
        requirement="OPERATOR"
      />
    );
  }

  return <MobileCameraStreamer />;
}
