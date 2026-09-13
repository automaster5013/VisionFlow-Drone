/** Reads a request stream without retaining more than the configured limit. */
export async function readBoundedRequestBody(
  body: ReadableStream<Uint8Array> | null,
  maxBytes: number,
): Promise<ArrayBuffer | null> {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 0) {
    throw new RangeError("maxBytes must be a non-negative safe integer");
  }
  if (!body) {
    return new ArrayBuffer(0);
  }

  const reader = body.getReader();
  const chunks: Uint8Array[] = [];
  let totalBytes = 0;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      totalBytes += value.byteLength;
      if (totalBytes > maxBytes) {
        await reader.cancel();
        return null;
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  const result = new ArrayBuffer(totalBytes);
  const output = new Uint8Array(result);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return result;
}

export type BoundedJsonResult =
  | { ok: true; value: unknown }
  | { ok: false; reason: "too_large" | "invalid" };

export type BoundedTextResult =
  | { ok: true; value: string }
  | { ok: false; reason: "too_large" | "invalid" };

/** Parses an upstream JSON response only after enforcing a byte ceiling. */
export async function readBoundedJsonResponse(
  response: Response,
  maxBytes: number,
): Promise<BoundedJsonResult> {
  try {
    const contentLength = response.headers.get("content-length");
    if (contentLength !== null) {
      if (!/^\d+$/.test(contentLength)) {
        return { ok: false, reason: "invalid" };
      }
      const declaredLength = Number(contentLength);
      if (!Number.isSafeInteger(declaredLength)) {
        return { ok: false, reason: "invalid" };
      }
      if (declaredLength > maxBytes) {
        await response.body?.cancel();
        return { ok: false, reason: "too_large" };
      }
    }

    const bytes = await readBoundedRequestBody(response.body, maxBytes);
    if (bytes === null) {
      return { ok: false, reason: "too_large" };
    }
    const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    return { ok: true, value: JSON.parse(text) as unknown };
  } catch {
    return { ok: false, reason: "invalid" };
  }
}

/** Reads UTF-8 text only after enforcing a byte ceiling on the stream. */
export async function readBoundedTextRequest(
  request: Request,
  maxBytes: number,
): Promise<BoundedTextResult> {
  const contentLength = request.headers.get("content-length");
  if (contentLength !== null) {
    if (!/^\d+$/.test(contentLength)) {
      return { ok: false, reason: "invalid" };
    }
    const declaredLength = Number(contentLength);
    if (!Number.isSafeInteger(declaredLength)) {
      return { ok: false, reason: "invalid" };
    }
    if (declaredLength > maxBytes) {
      return { ok: false, reason: "too_large" };
    }
  }

  try {
    const bytes = await readBoundedRequestBody(request.body, maxBytes);
    if (bytes === null) {
      return { ok: false, reason: "too_large" };
    }
    return {
      ok: true,
      value: new TextDecoder("utf-8", { fatal: true }).decode(bytes),
    };
  } catch {
    return { ok: false, reason: "invalid" };
  }
}

/** Parses JSON only after enforcing a byte ceiling while consuming the stream. */
export async function readBoundedJsonRequest(
  request: Request,
  maxBytes: number,
): Promise<BoundedJsonResult> {
  const contentLength = request.headers.get("content-length");
  if (contentLength !== null) {
    if (!/^\d+$/.test(contentLength)) {
      return { ok: false, reason: "invalid" };
    }
    const declaredLength = Number(contentLength);
    if (!Number.isSafeInteger(declaredLength)) {
      return { ok: false, reason: "invalid" };
    }
    if (declaredLength > maxBytes) {
      return { ok: false, reason: "too_large" };
    }
  }

  try {
    const bytes = await readBoundedRequestBody(request.body, maxBytes);
    if (bytes === null) {
      return { ok: false, reason: "too_large" };
    }
    const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    return { ok: true, value: JSON.parse(text) as unknown };
  } catch {
    return { ok: false, reason: "invalid" };
  }
}
