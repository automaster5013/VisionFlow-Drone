import test from 'node:test';
import assert from 'node:assert/strict';
import { telemetryReception } from '../src/lib/telemetry-reception.ts';

test('recent packet is live, expires without needing another packet', () => {
  assert.equal(telemetryReception(20000, 5000), 'LIVE');
  assert.equal(telemetryReception(20001, 5000), 'STALE');
});
test('missing or invalid timestamps cannot imply live reception', () => {
  assert.equal(telemetryReception(20000, null), 'WAITING');
  assert.equal(telemetryReception(20000, NaN), 'WAITING');
  assert.equal(telemetryReception(20000, 30000), 'STALE');
});
