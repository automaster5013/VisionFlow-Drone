const RETURN_TO_ORIGIN = "https://visionflow.invalid";

export function safeReturnTo(
  value: string | string[] | null | undefined,
  fallback = "/dashboard",
): string {
  const candidate = Array.isArray(value) ? value[0] : value;
  if (!candidate?.startsWith("/") || candidate.startsWith("//")) {
    return fallback;
  }

  try {
    const target = new URL(candidate, RETURN_TO_ORIGIN);
    if (target.origin !== RETURN_TO_ORIGIN) {
      return fallback;
    }
    return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    return fallback;
  }
}
