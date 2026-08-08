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


class SystemTraceabilityOperatorConsoleSettingsTest(unittest.TestCase):
    def test_current_operator_console_settings_is_complete(self) -> None:
        self.assertEqual(
            traceability.operator_console_settings_ui_policy_drift(
                SCRIPT_DIR.parent
            ),
            [],
        )

    def test_missing_page_mount_is_detected(self) -> None:
        drift = self.mutated_drift(
            Path("01_frontend/visionflow-web/src/app/settings/page.tsx"),
            "<OperatorConsoleSettingsCenter />",
            "<div />",
        )
        self.assertIn(
            "missing-token:settings-page:<OperatorConsoleSettingsCenter />",
            drift,
        )

    def test_missing_local_storage_write_is_detected(self) -> None:
        drift = self.mutated_drift(
            self.storage_relative_path(),
            "window.localStorage.setItem(",
            "window.sessionStorage.setItem(",
        )
        self.assertIn(
            "missing-token:settings-storage:window.localStorage.setItem(",
            drift,
        )

    def test_missing_event_integration_is_detected(self) -> None:
        drift = self.mutated_drift(
            self.events_relative_path(),
            "consolePreferences.eventTimeRange",
            '"24H"',
        )
        self.assertIn(
            "missing-token:events-center:"
            "consolePreferences.eventTimeRange",
            drift,
        )

    def test_missing_statistics_integration_is_detected(self) -> None:
        drift = self.mutated_drift(
            self.statistics_relative_path(),
            "consolePreferences.statisticsRangeDays",
            "30",
        )
        self.assertIn(
            "missing-token:statistics-center:"
            "consolePreferences.statisticsRangeDays",
            drift,
        )

    def test_missing_ai_model_integration_is_detected(self) -> None:
        drift = self.mutated_drift(
            self.models_relative_path(),
            "consolePreferences.aiModelAutoRefresh",
            "true",
        )
        self.assertIn(
            "missing-token:models-center:"
            "consolePreferences.aiModelAutoRefresh",
            drift,
        )

    def test_network_request_is_detected(self) -> None:
        drift = self.mutated_drift(
            self.center_relative_path(),
            "function save() {",
            'function save() {\n    fetch("/api/settings");',
        )
        self.assertIn(
            "usage:operator-console-settings:no-network-request", drift
        )

    def test_sensitive_storage_field_is_detected(self) -> None:
        drift = self.mutated_drift(
            self.storage_relative_path(),
            "const payload: StoredOperatorConsolePreferences = {",
            "const apiKey = preferences;\n  "
            "const payload: StoredOperatorConsolePreferences = {",
        )
        self.assertIn(
            "exposure:operator-console-settings:sensitive-value", drift
        )

    def test_missing_push_and_pr_trigger_is_detected(self) -> None:
        drift = self.mutated_drift(
            Path(".github/workflows/api-audit.yml"),
            '      - "01_frontend/visionflow-web/src/app/settings/**"\n',
            "",
        )
        self.assertIn(
            "trigger:operator-console-settings:push-and-pr:"
            '"01_frontend/visionflow-web/src/app/settings/**"',
            drift,
        )

    @staticmethod
    def center_relative_path() -> Path:
        return Path(
            "01_frontend/visionflow-web/src/components/settings/"
            "operator-console-settings-center.tsx"
        )

    @staticmethod
    def storage_relative_path() -> Path:
        return Path(
            "01_frontend/visionflow-web/src/lib/"
            "operator-console-settings.ts"
        )

    @staticmethod
    def events_relative_path() -> Path:
        return Path(
            "01_frontend/visionflow-web/src/components/events/"
            "event-operations-center.tsx"
        )

    @staticmethod
    def statistics_relative_path() -> Path:
        return Path(
            "01_frontend/visionflow-web/src/components/statistics/"
            "operations-statistics-center.tsx"
        )

    @staticmethod
    def models_relative_path() -> Path:
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
            return traceability.operator_console_settings_ui_policy_drift(
                root
            )

    def copy_policy_sources(self, target_root: Path) -> None:
        source_root = SCRIPT_DIR.parent
        relative_paths = [
            Path(".github/workflows/api-audit.yml"),
            Path("01_frontend/visionflow-web/src/app/settings/page.tsx"),
            self.center_relative_path(),
            self.storage_relative_path(),
            Path(
                "01_frontend/visionflow-web/src/types/"
                "operator-console-settings.ts"
            ),
            self.events_relative_path(),
            self.statistics_relative_path(),
            self.models_relative_path(),
        ]
        for relative_path in relative_paths:
            source = source_root / relative_path
            destination = target_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)


if __name__ == "__main__":
    unittest.main()
