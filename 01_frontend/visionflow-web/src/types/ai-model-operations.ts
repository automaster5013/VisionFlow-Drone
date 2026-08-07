export interface AiModelClass {
  id: number;
  name: string;
}

export interface AiModelStatus {
  profile: string | null;
  localFile: boolean;
  sizeBytes: number | null;
  sha256: string | null;
  classCount: number;
  classes: AiModelClass[];
  confidence: number | null;
  iou: number | null;
  imageSize: number | null;
  deviceRequested: string | null;
  deviceEffective: string | null;
  requireCuda: boolean;
  torchVersion: string | null;
  torchCudaVersion: string | null;
  cudnnVersion: number | null;
  cudaAvailable: boolean;
  cudaDeviceCount: number;
  cudaDeviceIndex: number | null;
  cudaDeviceName: string | null;
  cudaCapability: number[];
  cudaTotalMemoryBytes: number | null;
}

export interface AiIngestStatus {
  enabled: boolean;
  running: boolean;
  queueDepth: number;
  queueCapacity: number;
  acceptedFrames: number;
  droppedFrames: number;
  dropRatePct: number;
  inputFps: number;
  lastReceivedAt: string | null;
}

export interface AiStreamStatus {
  running: boolean;
  hasFrame: boolean;
  connectedClients: number;
  frameIndex: number | null;
  sourceId: string | null;
  sourceType: string | null;
  droneId: number | null;
  capturedAt: string | null;
  detectionCount: number;
}

export interface AiPerformanceHealth {
  status: string;
  reasonCodes: string[];
  evaluatedAt: string | null;
  inputToProcessingRatio: number | null;
  queueUtilizationPct: number | null;
}

export interface AiPerformanceStatus {
  running: boolean;
  startedAt: string | null;
  lastProcessedAt: string | null;
  uptimeSeconds: number;
  modelName: string;
  device: string;
  sourceType: string;
  configuredInputFps: number;
  processedFrames: number;
  detectedFrames: number;
  totalDetections: number;
  processingFps: number;
  averageInferenceMs: number;
  p95InferenceMs: number;
  maximumInferenceMs: number;
  rollingSampleCount: number;
  rollingWindowSeconds: number;
  health: AiPerformanceHealth;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function booleanValue(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function nullableNumber(value: unknown): number | null | undefined {
  return value === null ? null : numberValue(value) ?? undefined;
}

function nullableString(value: unknown): string | null | undefined {
  return value === null ? null : stringValue(value) ?? undefined;
}

export function parseAiModelStatus(value: unknown): AiModelStatus | null {
  if (!isRecord(value) || !Array.isArray(value.classes) || !Array.isArray(value.cudaCapability)) {
    return null;
  }
  const classes = value.classes.map((item) => {
    if (!isRecord(item)) return null;
    const id = numberValue(item.id);
    const name = stringValue(item.name);
    return id !== null && Number.isInteger(id) && name !== null ? { id, name } : null;
  });
  const capability = value.cudaCapability.map(numberValue);
  if (classes.some((item) => item === null) || capability.some((item) => item === null)) return null;

  const classCount = numberValue(value.classCount);
  const localFile = booleanValue(value.localFile);
  const requireCuda = booleanValue(value.requireCuda);
  const cudaAvailable = booleanValue(value.cudaAvailable);
  const cudaDeviceCount = numberValue(value.cudaDeviceCount);
  if (classCount === null || localFile === null || requireCuda === null || cudaAvailable === null || cudaDeviceCount === null) return null;

  return {
    profile: nullableString(value.profile) ?? null,
    localFile,
    sizeBytes: nullableNumber(value.sizeBytes) ?? null,
    sha256: nullableString(value.sha256) ?? null,
    classCount,
    classes: classes as AiModelClass[],
    confidence: nullableNumber(value.confidence) ?? null,
    iou: nullableNumber(value.iou) ?? null,
    imageSize: nullableNumber(value.imageSize) ?? null,
    deviceRequested: nullableString(value.deviceRequested) ?? null,
    deviceEffective: nullableString(value.deviceEffective) ?? null,
    requireCuda,
    torchVersion: nullableString(value.torchVersion) ?? null,
    torchCudaVersion: nullableString(value.torchCudaVersion) ?? null,
    cudnnVersion: nullableNumber(value.cudnnVersion) ?? null,
    cudaAvailable,
    cudaDeviceCount,
    cudaDeviceIndex: nullableNumber(value.cudaDeviceIndex) ?? null,
    cudaDeviceName: nullableString(value.cudaDeviceName) ?? null,
    cudaCapability: capability as number[],
    cudaTotalMemoryBytes: nullableNumber(value.cudaTotalMemoryBytes) ?? null,
  };
}

export function parseAiIngestStatus(value: unknown): AiIngestStatus | null {
  if (!isRecord(value)) return null;
  const enabled = booleanValue(value.enabled);
  const running = booleanValue(value.running);
  const queueDepth = numberValue(value.queueDepth);
  const queueCapacity = numberValue(value.queueCapacity);
  const acceptedFrames = numberValue(value.acceptedFrames);
  const droppedFrames = numberValue(value.droppedFrames);
  const dropRatePct = numberValue(value.dropRatePct);
  const inputFps = numberValue(value.inputFps);
  const lastReceivedAt = nullableString(value.lastReceivedAt);
  if (
    enabled === null ||
    running === null ||
    queueDepth === null ||
    queueCapacity === null ||
    acceptedFrames === null ||
    droppedFrames === null ||
    dropRatePct === null ||
    inputFps === null ||
    lastReceivedAt === undefined
  ) return null;
  return { enabled, running, queueDepth, queueCapacity, acceptedFrames, droppedFrames, dropRatePct, inputFps, lastReceivedAt };
}

export function parseAiStreamStatus(value: unknown): AiStreamStatus | null {
  if (!isRecord(value)) return null;
  const running = booleanValue(value.running);
  const hasFrame = booleanValue(value.hasFrame);
  const connectedClients = numberValue(value.connectedClients);
  const detectionCount = numberValue(value.detectionCount);
  const frameIndex = nullableNumber(value.frameIndex);
  const sourceId = nullableString(value.sourceId);
  const sourceType = nullableString(value.sourceType);
  const droneId = nullableNumber(value.droneId);
  const capturedAt = nullableString(value.capturedAt);
  if (running === null || hasFrame === null || connectedClients === null || detectionCount === null || frameIndex === undefined || sourceId === undefined || sourceType === undefined || droneId === undefined || capturedAt === undefined) return null;
  return { running, hasFrame, connectedClients, frameIndex, sourceId, sourceType, droneId, capturedAt, detectionCount };
}

export function parseAiPerformanceStatus(value: unknown): AiPerformanceStatus | null {
  if (!isRecord(value) || !isRecord(value.health)) return null;
  const healthStatus = stringValue(value.health.status);
  const reasonCodes = Array.isArray(value.health.reasonCodes) && value.health.reasonCodes.every((item) => typeof item === "string") ? value.health.reasonCodes as string[] : null;
  const fields = ["uptimeSeconds", "configuredInputFps", "processedFrames", "detectedFrames", "totalDetections", "processingFps", "averageInferenceMs", "p95InferenceMs", "maximumInferenceMs", "rollingSampleCount", "rollingWindowSeconds"] as const;
  const numbers = Object.fromEntries(fields.map((field) => [field, numberValue(value[field])])) as Record<(typeof fields)[number], number | null>;
  if (booleanValue(value.running) === null || healthStatus === null || reasonCodes === null || fields.some((field) => numbers[field] === null)) return null;
  const startedAt = nullableString(value.startedAt);
  const lastProcessedAt = nullableString(value.lastProcessedAt);
  if (startedAt === undefined || lastProcessedAt === undefined) return null;
  return {
    running: value.running as boolean,
    startedAt,
    lastProcessedAt,
    uptimeSeconds: numbers.uptimeSeconds!,
    modelName: stringValue(value.modelName) ?? "알 수 없음",
    device: stringValue(value.device) ?? "알 수 없음",
    sourceType: stringValue(value.sourceType) ?? "알 수 없음",
    configuredInputFps: numbers.configuredInputFps!,
    processedFrames: numbers.processedFrames!,
    detectedFrames: numbers.detectedFrames!,
    totalDetections: numbers.totalDetections!,
    processingFps: numbers.processingFps!,
    averageInferenceMs: numbers.averageInferenceMs!,
    p95InferenceMs: numbers.p95InferenceMs!,
    maximumInferenceMs: numbers.maximumInferenceMs!,
    rollingSampleCount: numbers.rollingSampleCount!,
    rollingWindowSeconds: numbers.rollingWindowSeconds!,
    health: {
      status: healthStatus,
      reasonCodes,
      evaluatedAt: nullableString(value.health.evaluatedAt) ?? null,
      inputToProcessingRatio: nullableNumber(value.health.inputToProcessingRatio) ?? null,
      queueUtilizationPct: nullableNumber(value.health.queueUtilizationPct) ?? null,
    },
  };
}
