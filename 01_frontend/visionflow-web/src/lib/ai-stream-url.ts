const DEFAULT_AI_STREAM_URL = "/api/ai/stream/annotated";

export function getAiStreamUrl(): string {
  const configured = process.env.NEXT_PUBLIC_AI_STREAM_URL?.trim();

  if (configured?.startsWith("/") && !configured.startsWith("//")) {
    return configured;
  }

  return DEFAULT_AI_STREAM_URL;
}
