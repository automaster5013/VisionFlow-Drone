import assert from 'node:assert/strict';
import test from 'node:test';
import { presentationTelemetry as point } from '../src/lib/presentation-telemetry.ts';
const origin = {latitude:37.5665,longitude:126.978};
test('video-clock positions are deterministic and simulation-marked', () => {
  assert.deepEqual(point(39,107,origin),point(39,107,origin));
  assert.equal(point(39,107,origin).telemetrySource,'SIMULATOR');
});
test('complete loop returns to origin and lands', () => {
  const a=point(0,107,origin), b=point(107,107,origin);
  assert.ok(Math.abs(a.latitude-b.latitude)<1e-8 && Math.abs(a.longitude-b.longitude)<1e-8);
  assert.equal(a.altitude,0); assert.equal(b.altitude,0); assert.equal(b.groundSpeed,0);
  assert.equal(a.batteryLevel,100); assert.equal(b.batteryLevel,85);
});
test('all generated values stay inside telemetry bounds', () => {
  for(let s=0;s<=107;s+=.25){const p=point(s,107,origin); assert.ok(p.altitude>=0&&p.altitude<=30);assert.ok(p.heading>=0&&p.heading<360);assert.ok(p.batteryLevel>=85&&p.batteryLevel<=100);}
});
test('invalid timing and coordinates are rejected', () => {
  for(const d of [0,-1,NaN,Infinity])assert.throws(()=>point(0,d,origin));
  assert.throws(()=>point(0,107,{latitude:90,longitude:0}));
});
