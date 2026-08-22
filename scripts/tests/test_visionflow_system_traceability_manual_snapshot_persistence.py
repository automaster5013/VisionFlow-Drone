from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SystemTraceabilityManualSnapshotPersistenceTest(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_manual_snapshot_path_is_explicit_role_gated_and_audited(self) -> None:
        controller = self.read(
            "02_backend/visionflow-api/src/main/java/com/visionflow/api/ai/"
            "controller/AiInferenceEventController.java"
        )
        audit_action = self.read(
            "02_backend/visionflow-api/src/main/java/com/visionflow/api/audit/"
            "domain/AuditAction.java"
        )
        route = self.read(
            "01_frontend/visionflow-web/src/app/api/ai/events/[id]/snapshot/"
            "route.ts"
        )
        page = self.read("01_frontend/visionflow-web/src/app/events/page.tsx")
        center = self.read(
            "01_frontend/visionflow-web/src/components/events/"
            "event-operations-center.tsx"
        )
        drawer = self.read(
            "01_frontend/visionflow-web/src/components/events/"
            "event-detail-drawer.tsx"
        )
        control = self.read(
            "01_frontend/visionflow-web/src/components/events/"
            "manual-snapshot-control.tsx"
        )
        docs = self.read("docs/README-security-configuration.md")

        self.assertIn("PRIVACY_SNAPSHOT_STORED", audit_action)
        self.assertIn("AuditAction.PRIVACY_SNAPSHOT_STORED", controller)
        self.assertIn('"MANUAL_OPERATOR"', controller)
        self.assertIn('"AI_INTERNAL"', controller)
        self.assertIn("Authentication authentication", controller)

        for token in (
            "export async function PUT",
            "rejectCrossOriginOperatorMutation(request)",
            "await request.formData()",
            'method: "PUT"',
            "withBackendOperatorAuth",
        ):
            self.assertIn(token, route)

        self.assertIn(
            'Accept: "image/jpeg, application/json"',
            route,
        )
        self.assertNotIn(
            'Accept: "image/jpeg",',
            route,
        )

        self.assertIn("requireOperatorAuthentication", page)
        self.assertIn("requireOperatorPageAccess", page)
        self.assertIn('"OPERATOR"', page)
        self.assertIn("canManageSnapshots={canManageSnapshots}", page)

        self.assertIn("canManageSnapshots?: boolean", center)
        self.assertIn("canManageSnapshots = false", center)
        self.assertIn(
            "onSnapshotStored={() => void refresh(true)}",
            center,
        )
        self.assertIn("ManualSnapshotControl", drawer)
        normalized_drawer = " ".join(drawer.split())
        self.assertIn(
            "canManageSnapshots && event.snapshotEventId !== null",
            normalized_drawer,
        )

        self.assertIn('type="file"', control)
        self.assertIn('accept=".jpg,.jpeg,image/jpeg"', control)
        self.assertIn("new FormData()", control)
        self.assertIn('method: "PUT"', control)
        self.assertIn('type="checkbox"', control)
        self.assertIn("자동 저장은 OFF 상태", control)

        for prohibited in (
            "getUserMedia",
            "mediaDevices",
            "captureStream",
            "drawImage(",
            "toDataURL(",
            "toBlob(",
        ):
            self.assertNotIn(prohibited, control)

        self.assertIn("SnapshotPolicy=OFF", docs)
        self.assertIn("PRIVACY_SNAPSHOT_STORED", docs)

    def test_api_baselines_follow_new_frontend_put(self) -> None:
        contract = json.loads(
            self.read("scripts/visionflow_api_contract_baseline.json")
        )
        security = json.loads(
            self.read("scripts/visionflow_api_security_baseline.json")
        )
        ci_policy = json.loads(
            self.read("scripts/visionflow_ci_api_audit_policy.json")
        )
        traceability = json.loads(
            self.read("scripts/visionflow_system_traceability_baseline.json")
        )

        self.assertEqual(83, contract["expectedCounts"]["frontend"])
        self.assertEqual(83, security["expectedCounts"]["frontend"])
        self.assertEqual(83, ci_policy["expectedCounts"]["frontend"])
        self.assertEqual(
            83,
            ci_policy["expectedTraceabilityCounts"]["frontend"],
        )
        self.assertEqual(83, traceability["expectedCounts"]["frontend"])

        backend_only = {
            (item["method"], item["path"])
            for item in contract["expectedBackendOnlyOperations"]
        }
        self.assertNotIn(
            ("PUT", "/api/ai/events/{}/snapshot"),
            backend_only,
        )

        ai_flow = next(
            flow
            for flow in traceability["flows"]
            if flow["key"] == "ai-event-alert"
        )
        self.assertTrue(
            any(
                "GET|PUT|PATCH|DELETE" in pattern
                for pattern in ai_flow["frontendPatterns"]
            )
        )


if __name__ == "__main__":
    unittest.main()
