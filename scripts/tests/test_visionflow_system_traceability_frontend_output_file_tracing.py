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


class SystemTraceabilityFrontendOutputFileTracingTest(unittest.TestCase):
    def test_current_frontend_output_file_tracing_is_bounded(self) -> None:
        root = SCRIPT_DIR.parent
        self.assertEqual(
            traceability.frontend_output_file_tracing_policy_drift(root),
            [],
        )

    def test_missing_dynamic_file_ignore_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            loader = (
                root
                / "01_frontend/visionflow-web/src/lib/mobile-evidence.ts"
            )
            source = loader.read_text(encoding="utf-8")
            source = source.replace(
                "/*turbopackIgnore: true*/ directory",
                "directory",
                1,
            )
            loader.write_text(source, encoding="utf-8")

            drift = (
                traceability.frontend_output_file_tracing_policy_drift(root)
            )

        self.assertIn(
            "usage:mobile-evidence:three-bounded-nft-ignore-markers",
            drift,
        )

    def test_parent_directory_fallback_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.copy_policy_sources(root)
            loader = (
                root
                / "01_frontend/visionflow-web/src/lib/mobile-evidence.ts"
            )
            source = loader.read_text(encoding="utf-8")
            source = source.replace(
                "const candidates = [\n        configuredDirectory,",
                'const candidates = [\n        "..",\n'
                "        configuredDirectory,",
                1,
            )
            loader.write_text(source, encoding="utf-8")

            drift = (
                traceability.frontend_output_file_tracing_policy_drift(root)
            )

        self.assertIn(
            "scope:mobile-evidence:candidate-directories-"
            "remain-inside-frontend-root",
            drift,
        )

    def copy_policy_sources(self, target_root: Path) -> None:
        source_root = SCRIPT_DIR.parent
        relative_paths = [
            Path(
                "01_frontend/visionflow-web/src/lib/mobile-evidence.ts"
            ),
            Path(
                "01_frontend/visionflow-web/src/app/api/mobile/evidence"
                "/status/route.ts"
            ),
            Path("01_frontend/visionflow-web/next.config.ts"),
            Path("compose.yaml"),
        ]
        for relative_path in relative_paths:
            source = source_root / relative_path
            target = target_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


if __name__ == "__main__":
    unittest.main()
