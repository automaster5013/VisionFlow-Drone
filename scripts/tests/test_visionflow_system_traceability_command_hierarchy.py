from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ROOT / "01_frontend" / "visionflow-web" / "src"
CSS_PATH = WEB_ROOT / "app" / "globals.css"


class SharedCommandHierarchyTraceabilityTest(unittest.TestCase):
    def test_eight_primary_surfaces_keep_semantic_hierarchy_hooks(self) -> None:
        hooks = {
            WEB_ROOT / "components" / "dashboard" / "operations-dashboard.tsx":
                "vf-operations-dashboard__hero",
            WEB_ROOT / "components" / "drones" / "drone-fleet-control.tsx":
                "vf-fleet-map-title",
            WEB_ROOT / "components" / "mobile" / "mobile-camera-streamer.tsx":
                "vf-camera-command__hero",
            WEB_ROOT / "components" / "events" / "event-operations-center.tsx":
                "vf-event-command__hero",
            WEB_ROOT / "app" / "audit-logs" / "page.tsx":
                "vf-audit-command__hero",
            WEB_ROOT / "app" / "security-status" / "page.tsx":
                "vf-security-command__hero",
            WEB_ROOT / "components" / "statistics" / "operations-statistics-center.tsx":
                "vf-statistics-command__hero",
            WEB_ROOT / "components" / "models" / "ai-model-operations-center.tsx":
                "vf-model-command__hero",
        }

        for path, hook in hooks.items():
            with self.subTest(path=path):
                source = path.read_text(encoding="utf-8")
                self.assertIn(hook, source)

    def test_phase_1j_defines_shared_desktop_hierarchy(self) -> None:
        css = CSS_PATH.read_text(encoding="utf-8")

        self.assertIn(
            "Phase 1J: shared top-level information hierarchy across command surfaces",
            css,
        )
        for token in (
            ".vf-operations-dashboard__hero",
            ".vf-camera-command__hero",
            ".vf-event-command__hero",
            ".vf-audit-command__hero",
            ".vf-security-command__hero",
            ".vf-statistics-command__hero",
            ".vf-model-command__hero",
            ".vf-fleet-map-title",
            "min-height: 168px",
            "font-size: 2.25rem",
            "font-weight: 900",
            "letter-spacing: -0.035em",
            "max-width: 1500px !important",
        ):
            with self.subTest(token=token):
                self.assertIn(token, css)

    def test_compact_map_and_mobile_hierarchy_are_preserved(self) -> None:
        css = CSS_PATH.read_text(encoding="utf-8")

        self.assertIn(".vf-fleet-map-title h1", css)
        self.assertIn("font-size: 1.875rem", css)
        self.assertIn("@media (max-width: 767px)", css)
        self.assertIn("font-size: 1.75rem", css)
        self.assertIn("font-size: 1.625rem", css)

    def test_phase_does_not_change_runtime_or_security_contracts(self) -> None:
        css = CSS_PATH.read_text(encoding="utf-8")
        phase = css.split(
            "/* Phase 1J: shared top-level information hierarchy across command surfaces. */",
            1,
        )[1].split("/* Phase 1A bridge:", 1)[0]

        for forbidden in (
            "/api/",
            "fetch(",
            "Authorization",
            "operatorSession",
            "VISIONFLOW_",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, phase)


if __name__ == "__main__":
    unittest.main()
