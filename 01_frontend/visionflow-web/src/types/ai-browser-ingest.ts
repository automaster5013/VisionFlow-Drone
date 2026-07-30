export interface AiBrowserIngestStatus {
  enabled: boolean;
  running: boolean;
  queueDepth: number;
  acceptedFrames: number;
  droppedFrames: number;
  lastReceivedAt: string | null;
}

export interface AiBrowserFrameUploadResponse {
  accepted: boolean;
  droppedPreviousFrame: boolean;
  queueDepth: number;
  acceptedFrames: number;
  droppedFrames: number;
}
