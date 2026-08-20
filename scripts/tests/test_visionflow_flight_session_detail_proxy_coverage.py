from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_api_contract_audit as contract
import visionflow_api_security_audit as security


class FlightSessionDetailProxyCoverageTest(unittest.TestCase):
    def test_current_detail_proxy_is_covered_and_authenticated(self) -> None:
        root = SCRIPT_DIR.parent
        key = ("GET", "/api/drones/{}/flight-sessions/{}")
        operations = contract.parse_frontend_operations(root)
        operation = next(item for item in operations if item.key == key)
        route_text = (root / operation.source).read_text(encoding="utf-8")

        self.assertEqual(
            security.route_auth_mechanism(
                operation,
                route_text,
                security.helper_auth_modules(root),
            ),
            "OPERATOR_AUTH",
        )
        self.assertIn('method: "GET"', route_text)
        self.assertIn('cache: "no-store"', route_text)
        self.assertIn("AbortSignal.timeout(10_000)", route_text)

        contract_baseline = json.loads(
            (SCRIPT_DIR / "visionflow_api_contract_baseline.json")
            .read_text(encoding="utf-8")
        )
        security_baseline = json.loads(
            (SCRIPT_DIR / "visionflow_api_security_baseline.json")
            .read_text(encoding="utf-8")
        )
        policy = json.loads(
            (SCRIPT_DIR / "visionflow_ci_api_audit_policy.json")
            .read_text(encoding="utf-8")
        )

        expected_frontend = contract_baseline["expectedCounts"]["frontend"]
        self.assertEqual(len(operations), expected_frontend)
        self.assertEqual(
            security_baseline["expectedCounts"]["frontend"],
            expected_frontend,
        )
        self.assertEqual(
            policy["expectedCounts"]["frontend"],
            expected_frontend,
        )
        self.assertEqual(contract_baseline["advisoryBackendOnlyOperations"], [])
        self.assertEqual(policy["allowedContractAdvisories"], [])

    def test_operator_password_manual_session_forward_is_authenticated(
        self,
    ) -> None:
        root = SCRIPT_DIR.parent
        key = ("POST", "/api/operator/password")
        operations = contract.parse_frontend_operations(root)
        operation = next(item for item in operations if item.key == key)
        route_text = (root / operation.source).read_text(encoding="utf-8")

        self.assertEqual(
            security.route_auth_mechanism(
                operation,
                route_text,
                security.helper_auth_modules(root),
            ),
            "OPERATOR_AUTH",
        )
        self.assertEqual(
            security.route_mutation_guard(operation, route_text),
            "SAME_ORIGIN_MANUAL",
        )

    def test_missing_operator_auth_is_detected(self) -> None:
        operation = contract.Operation(
            method="GET",
            path="/api/drones/[id]/flight-sessions/[sessionId]",
            source="route.ts",
            handler="GET",
        )
        unsafe_route = """
            export async function GET() {
              return fetch('/api/drones/1/flight-sessions/session-1');
            }
        """

        self.assertEqual(
            security.route_auth_mechanism(operation, unsafe_route, set()),
            "NONE",
        )


if __name__ == "__main__":
    unittest.main()
