import test from "node:test";
import assert from "node:assert/strict";
import { hasActivePresentation, fleetFlightState } from "../src/lib/fleet-presentation-status.ts";
const session = { droneId: 3, managed: true, status: "ACTIVE", sourceDeviceId: "presentation-simulator-001" };
test("only owned active presentation sessions qualify", () => {
  assert.equal(hasActivePresentation([session], 3), true);
  for (const change of [{ status: "COMPLETED" }, { status: "ABORTED" }, { managed: false }, { droneId: 2 }, { sourceDeviceId: "phone" }]) {
    assert.equal(hasActivePresentation([{ ...session, ...change }], 3), false);
  }
  assert.equal(hasActivePresentation(null, 3), false);
});
test("fresh simulation is counted without changing physical OFFLINE state", () => {
  const drone = { status: "OFFLINE", isStale: false };
  assert.deepEqual(fleetFlightState(drone, true), { simulated: true, actual: false, label: "시연 중" });
  assert.equal(drone.status, "OFFLINE");
});
test("stale simulation is waiting and excluded; completed simulation clears", () => {
  assert.deepEqual(fleetFlightState({ status: "OFFLINE", isStale: true }, true), { simulated: false, actual: false, label: "시연 데이터 대기" });
  assert.equal(fleetFlightState({ status: "OFFLINE", isStale: false }, false).label, "OFFLINE");
});
test("real flights count once, stale flights do not count", () => {
  assert.equal(fleetFlightState({ status: "FLYING", isStale: false }, false).actual, true);
  assert.equal(fleetFlightState({ status: "FLYING", isStale: true }, false).actual, false);
  assert.equal(fleetFlightState({ status: "FLYING", isStale: false }, true).actual, false);
});
