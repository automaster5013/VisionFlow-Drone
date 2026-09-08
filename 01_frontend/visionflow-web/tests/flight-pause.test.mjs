import test from 'node:test';
import assert from 'node:assert/strict';
import { pausedSecondsBetween } from '../src/lib/flight-pause.ts';
const time = s => `2026-09-09T00:00:${String(s).padStart(2, '0')}Z`;
test('only confirmed pause overlap is subtracted; real residual gap remains', () => {
  const pauses = [{pausedAt:time(5),resumedAt:time(20)}];
  assert.equal(30-pausedSecondsBetween(Date.parse(time(0)),Date.parse(time(30)),pauses),15);
  assert.equal(pausedSecondsBetween(Date.parse(time(17)),Date.parse(time(23)),pauses),3);
  assert.equal(pausedSecondsBetween(Date.parse(time(0)),Date.parse(time(30)),[{pausedAt:time(5),resumedAt:null}]),0);
});
test('overlapping and invalid records cannot double-discount a gap', () => {
  assert.equal(pausedSecondsBetween(Date.parse(time(0)),Date.parse(time(30)),[
    {pausedAt:time(5),resumedAt:time(20)},{pausedAt:time(10),resumedAt:time(25)},
    {pausedAt:'invalid',resumedAt:time(30)}]),20);
});
