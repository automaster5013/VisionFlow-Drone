import assert from 'node:assert/strict';
import test from 'node:test';

import {
  readBoundedJsonRequest,
  readBoundedJsonResponse,
  readBoundedRequestBody,
  readBoundedTextRequest,
} from '../src/lib/request-body-limit.ts';

test('reads a request body up to the exact byte limit', async () => {
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(new Uint8Array([1, 2]));
      controller.enqueue(new Uint8Array([3]));
      controller.close();
    },
  });

  assert.deepEqual(
    new Uint8Array(await readBoundedRequestBody(body, 3)),
    new Uint8Array([1, 2, 3]),
  );
});

test('bounds JSON responses from upstream services', async () => {
  const response = new Response(JSON.stringify({ ok: true }));
  assert.deepEqual(await readBoundedJsonResponse(response, 32), {
    ok: true,
    value: { ok: true },
  });

  const tooLarge = new Response(JSON.stringify({ payload: 'x'.repeat(32) }));
  assert.deepEqual(await readBoundedJsonResponse(tooLarge, 16), {
    ok: false,
    reason: 'too_large',
  });
});

test('cancels an oversized request as soon as the limit is crossed', async () => {
  let cancelled = false;
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(new Uint8Array([1, 2]));
      controller.enqueue(new Uint8Array([3, 4]));
    },
    cancel() {
      cancelled = true;
    },
  });

  assert.equal(await readBoundedRequestBody(body, 3), null);
  assert.equal(cancelled, true);
});

test('rejects invalid byte limits', async () => {
  await assert.rejects(
    readBoundedRequestBody(null, Number.POSITIVE_INFINITY),
    RangeError,
  );
});

test('parses JSON only within the configured request byte limit', async () => {
  const request = new Request('https://example.test', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ ok: true }),
  });

  assert.deepEqual(await readBoundedJsonRequest(request, 32), {
    ok: true,
    value: { ok: true },
  });
});

test('rejects JSON requests whose declared or streamed length exceeds the limit', async () => {
  const declaredLarge = new Request('https://example.test', {
    method: 'POST',
    headers: { 'content-length': '100' },
    body: '{}',
  });
  assert.deepEqual(await readBoundedJsonRequest(declaredLarge, 8), {
    ok: false,
    reason: 'too_large',
  });

  const streamedLarge = new Request('https://example.test', {
    method: 'POST',
    body: '123456789',
  });
  assert.deepEqual(await readBoundedJsonRequest(streamedLarge, 8), {
    ok: false,
    reason: 'too_large',
  });
});

test('rejects malformed JSON and invalid content-length metadata', async () => {
  const malformed = new Request('https://example.test', {
    method: 'POST',
    body: '{',
  });
  assert.deepEqual(await readBoundedJsonRequest(malformed, 8), {
    ok: false,
    reason: 'invalid',
  });
});

test('bounds UTF-8 text requests by bytes, including non-ASCII input', async () => {
  const oversizedUtf8 = new Request('https://example.test', {
    method: 'POST',
    body: '한글한글',
  });
  assert.deepEqual(await readBoundedTextRequest(oversizedUtf8, 8), {
    ok: false,
    reason: 'too_large',
  });

  const valid = new Request('https://example.test', {
    method: 'POST',
    body: 'hello',
  });
  assert.deepEqual(await readBoundedTextRequest(valid, 5), {
    ok: true,
    value: 'hello',
  });
});
