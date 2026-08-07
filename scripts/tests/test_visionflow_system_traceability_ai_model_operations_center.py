from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import visionflow_system_traceability_audit as traceability


class SystemTraceabilityAiModelOperationsCenterTest(unittest.TestCase):
    def test_current_ai_model_operations_center_is_complete(self) -> None:
        self.assertEqual(
            traceability.ai_model_operations_center_ui_policy_drift(
                SCRIPT_DIR.parent
            ),
            [],
        )

    def test_missing_page_mount_is_detected(self) -> None:
        drift = self.mutated_drift(
            Path("01_frontend/visionflow-web/src/app/models/page.tsx"),
            "<AiModelOperationsCenter />",
            "<div />",
        )
        self.assertIn(
            "missing-token:models-page:<AiModelOperationsCenter />", drift
        )

    def test_missing_partial_failure_isolation_is_detected(self) -> None:
        drift = self.mutated_drift(
            self.center_relative_path(),
            "Promise.allSettled([",
            "Promise.all([",
        )
        self.assertIn(
            "missing-token:models-center:Promise.allSettled([", drift
        )

    def test_missing_model_parser_is_detected(self) -> None:
        drift = self.mutated_drift(
            self.center_relative_path(),
            "parseAiModelStatus(modelResult.value)",
            "modelResult.value",
        )
        self.assertIn(
            "missing-token:models-center:"
            "parseAiModelStatus(modelResult.value)",
            drift,
        )

    def test_missing_auto_refresh_is_detected(self) -> None:
        drift = self.mutated_drift(
            self.center_relative_path(),
            "const AUTO_REFRESH_INTERVAL_MS = 30_000",
            "const AUTO_REFRESH_INTERVAL_MS = 60_000",
        )
        self.assertIn(
            "missing-token:models-center:"
            "const AUTO_REFRESH_INTERVAL_MS = 30_000",
            drift,
        )

    def test_missing_model_route_auth_is_detected(self) -> None:
        drift = self.mutated_drift(
            Path(
                "01_frontend/visionflow-web/src/app/api/ai/models/status/route.ts"
            ),
            "getOperatorSecurityStatus()",
            "Promise.resolve(null)",
        )
        self.assertIn(
            "missing-token:model-status-route:getOperatorSecurityStatus()",
            drift,
        )

    def test_raw_model_path_exposure_is_detected(self) -> None:
        drift = self.mutated_drift(
            Path(
                "01_frontend/visionflow-web/src/app/api/ai/models/status/route.ts"
            ),
            "profile: nullableString(value.profile),",
            "requestedPath: value.requestedPath,",
        )
        self.assertIn(
            "exposure:model-status-route:raw-model-path", drift
        )

    def test_mutation_method_is_detected(self) -> None:
        drift = self.mutated_drift(
            self.center_relative_path(),
            'method: "GET"',
            'method: "POST"',
        )
        self.assertIn(
            "usage:ai-model-operations:center-read-only-no-mutation", drift
        )

    def test_missing_push_and_pr_trigger_is_detected(self) -> None:
        drift = self.mutated_drift(
            Path(".github/workflows/api-audit.yml"),
            '      - "01_frontend/visionflow-web/src/app/models/**"\n',
            "",
        )
        self.assertIn(
            "trigger:ai-model-operations:push-and-pr:"
            '"01_frontend/visionflow-web/src/app/models/**"',
            drift,
        )

    @staticmethod
    def center_relative_path() -> Path:
        return Path(
            "01_frontend/visionflow-web/src/components/models/"
            "ai-model-operations-center.tsx"
        )

    def mutated_drift(
        self, relative_path: Path, old: str, new: str
    ) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            path = root / relative_path
            source = path.read_text(encoding="utf-8")
            self.assertIn(old, source)
            path.write_text(source.replace(old, new, 1), encoding="utf-8")
            return traceability.ai_model_operations_center_ui_policy_drift(
                root
            )

    def copy_policy_sources(self, target_root: Path) -> None:
        source_root = SCRIPT_DIR.parent
        relative_paths = [
            Path(".github/workflows/api-audit.yml"),
            Path("01_frontend/visionflow-web/src/app/models/page.tsx"),
            self.center_relative_path(),
            Path("01_frontend/visionflow-web/src/types/ai-model-operations.ts"),
            Path(
                "01_frontend/visionflow-web/src/app/api/ai/models/status/route.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/app/api/ai/metrics/status/route.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/app/api/ai/ingest/status/route.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/app/api/ai/stream/status/route.ts"
            ),
            Path("01_frontend/visionflow-web/src/app/api/ai/alerts/route.ts"),
        ]
        for relative_path in relative_paths:
            source = source_root / relative_path
            destination = target_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)


if __name__ == "__main__":
    unittest.main()
