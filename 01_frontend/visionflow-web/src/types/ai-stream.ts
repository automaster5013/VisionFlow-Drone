import type { AiVideoSourceType } from "@/types/ai-inference-event";

export interface AiStreamStatus {
  running: boolean;
  hasFrame: boolean;
  connectedClients: number;
  frameIndex: number | null;
  sourceId: string | null;
  sourceType: AiVideoSourceType | null;
  droneId: number | null;
  capturedAt: string | null;
  detectionCount: number;
}
