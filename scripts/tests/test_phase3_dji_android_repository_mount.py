from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SIMULATOR_DIR = ROOT / "scripts" / "phase3-dji-simulator"
ENCODED_GATE = SIMULATOR_DIR / "phase3_dji_android_bridge_gate.py"
ROBUSTNESS_GATE = SIMULATOR_DIR / "phase3_dji_android_bridge_robustness.py"


class Phase3DjiAndroidRepositoryMountTest(unittest.TestCase):
    def test_encoded_ingress_full_suite_has_repository_contract(self) -> None:
        source = ENCODED_GATE.read_text(encoding="utf-8")

        self.assertEqual(
            source.count('"VISIONFLOW_REPOSITORY_ROOT=/repo"'),
            1,
        )
        self.assertEqual(source.count('f"{root}:/repo:ro"'), 1)

    def test_both_robustness_suites_have_repository_contract(self) -> None:
        source = ROBUSTNESS_GATE.read_text(encoding="utf-8")

        self.assertEqual(
            source.count('"VISIONFLOW_REPOSITORY_ROOT=/repo"'),
            2,
        )
        self.assertIn('repository_mount = f"{root}:/repo:ro"', source)
        self.assertEqual(source.count("repository_mount,"), 2)

    def test_all_repository_mounts_are_read_only(self) -> None:
        combined = "\n".join(
            (
                ENCODED_GATE.read_text(encoding="utf-8"),
                ROBUSTNESS_GATE.read_text(encoding="utf-8"),
            )
        )

        self.assertNotIn('f"{root}:/repo"', combined)
        self.assertNotIn('repository_mount = f"{root}:/repo"', combined)
        self.assertEqual(combined.count(':/repo:ro"'), 2)


if __name__ == "__main__":
    unittest.main()
