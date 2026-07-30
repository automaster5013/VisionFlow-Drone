import type { Metadata } from "next";

import { MobileCameraStreamer } from "@/components/mobile/mobile-camera-streamer";

export const metadata: Metadata = {
  title: "노트북 AI 카메라",
  description: "노트북 웹캠 영상을 VisionFlow AI 서버로 전송하고 분석 상태를 확인합니다.",
};

export default function MobileCameraPage() {
  return <MobileCameraStreamer />;
}
