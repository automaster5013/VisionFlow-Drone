export type AiVideoSourceType = "SMARTPHONE_LIVE" | "DUMMY_VIDEO" | "DJI_LIVE";

export interface AiDetection {
  id: number;
  classId: number;
  className: string;
  confidence: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface AiInferenceEvent {
  id: number;
  sourceId: string;
  sessionId: string;
  sourceType: AiVideoSourceType;
  droneId: number;
  frameIndex: number;
  capturedAt: string;
  receivedAt: string;
  inferenceMs: number;
  detectionCount: number;
  snapshotAvailable: boolean;
  snapshotUrl: string | null;
  snapshotSizeBytes: number | null;
  snapshotCreatedAt: string | null;
  detections: AiDetection[];
}
