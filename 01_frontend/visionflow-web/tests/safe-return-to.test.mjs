import assert from "node:assert/strict";
import { test } from "node:test";

import { safeReturnTo } from "../src/lib/safe-return-to.ts";

test("preserves same-origin return paths and query strings", () => {
  assert.equal(safeReturnTo("/dashboard?tab=events#latest"), "/dashboard?tab=events#latest");
});

test("rejects protocol-relative and absolute external URLs", () => {
  assert.equal(safeReturnTo("//evil.example"), "/dashboard");
  assert.equal(safeReturnTo("https://evil.example"), "/dashboard");
});

test("rejects backslash authority separators after URL normalization", () => {
  assert.equal(safeReturnTo("/\\evil.example"), "/dashboard");
});

test("uses the caller fallback for missing or repeated query values", () => {
  assert.equal(safeReturnTo(null, "/mobile-flight"), "/mobile-flight");
  assert.equal(safeReturnTo(["/\\evil.example", "/drones"], "/mobile-flight"), "/mobile-flight");
});
