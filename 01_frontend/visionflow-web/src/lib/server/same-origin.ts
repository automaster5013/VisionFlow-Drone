import "server-only";

import type { NextRequest } from "next/server";

export function isSameOriginRequest(request: NextRequest): boolean {
  if (request.headers.get("sec-fetch-site") === "same-origin") {
    return true;
  }

  const origin = request.headers.get("origin");
  if (origin === null) {
    return true;
  }

  try {
    const originUrl = new URL(origin);
    if (originUrl.protocol !== "http:" && originUrl.protocol !== "https:") {
      return false;
    }

    const forwardedHost = request.headers
      .get("x-forwarded-host")
      ?.split(",")[0]
      ?.trim();
    const requestHost = forwardedHost || request.headers.get("host")?.trim();
    if (!requestHost || originUrl.host.toLowerCase() !== requestHost.toLowerCase()) {
      return false;
    }

    const forwardedProtocol = request.headers
      .get("x-forwarded-proto")
      ?.split(",")[0]
      ?.trim()
      .toLowerCase();
    const requestProtocol =
      forwardedProtocol || request.nextUrl.protocol.replace(/:$/, "");

    return originUrl.protocol === `${requestProtocol}:`;
  } catch {
    return false;
  }
}
