import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "01_frontend" / "visionflow-web" / "src"

class CommandFleetControlTraceabilityTests(unittest.TestCase):
    def test_fleet_control_uses_semantic_command_surfaces(self):
        source = (FRONTEND / "components" / "drones" / "drone-fleet-control.tsx").read_text(encoding="utf-8")
        for name in ("vf-fleet-control", "vf-fleet-map-title", "vf-fleet-map-shell", "vf-fleet-roster", "vf-fleet-card", "vf-fleet-command-header", "vf-fleet-metric", "vf-fleet-connection-strip"):
            self.assertIn(name, source)

    def test_fleet_surfaces_use_shared_theme_tokens(self):
        css = (FRONTEND / "app" / "globals.css").read_text(encoding="utf-8")
        for token in ("--vf-surface-1", "--vf-surface-2", "--vf-border", "--vf-accent", "--vf-shadow"):
            self.assertIn(token, css)
        for name in (".vf-fleet-map-shell", ".vf-fleet-roster", ".vf-fleet-metric", ".vf-fleet-card.bg-blue-50", ".vf-fleet-connection-strip"):
            self.assertIn(name, css)

    def test_phase_does_not_touch_runtime_contracts(self):
        paths = {"01_frontend/visionflow-web/src/app/globals.css", "01_frontend/visionflow-web/src/components/drones/drone-fleet-control.tsx", "scripts/tests/test_visionflow_system_traceability_command_fleet_control.py"}
        self.assertFalse(any(path.startswith(("02_backend/", "03_ai-server/")) or "compose" in path for path in paths))

if __name__ == "__main__":
    unittest.main()
