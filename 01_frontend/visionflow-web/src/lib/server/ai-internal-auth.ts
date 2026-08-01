import "server-only";

export const AI_INTERNAL_KEY_HEADER = "X-VisionFlow-AI-Key";

export function withAiInternalAuth(init: RequestInit = {}): RequestInit {
  const internalKey = process.env.VISIONFLOW_AI_INTERNAL_KEY?.trim();

  if (!internalKey || internalKey.length < 32) {
    throw new Error("VisionFlow AI 내부 서비스 키가 설정되지 않았습니다.");
  }

  const headers = new Headers(init.headers);
  headers.delete(AI_INTERNAL_KEY_HEADER);
  headers.set(AI_INTERNAL_KEY_HEADER, internalKey);

  return {
    ...init,
    headers,
  };
}
