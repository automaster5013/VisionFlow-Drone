import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "01_frontend" / "visionflow-web" / "src"

class CommandDashboardTraceabilityTests(unittest.TestCase):
    def test_dashboard_uses_semantic_command_surfaces(self):
        source = (FRONTEND / "components" / "dashboard" / "operations-dashboard.tsx").read_text(encoding="utf-8")
        for name in ("vf-operations-dashboard", "vf-operations-dashboard__hero", "vf-command-panel", "vf-command-metric", "vf-command-counter", "vf-command-record", "vf-command-empty"):
            self.assertIn(name, source)

    def test_command_surfaces_use_theme_tokens(self):
        css = (FRONTEND / "app" / "globals.css").read_text(encoding="utf-8")
        for token in ("--vf-surface-1", "--vf-surface-2", "--vf-border", "--vf-accent", "--vf-warning"):
            self.assertIn(token, css)
        self.assertIn(".vf-operations-dashboard__hero", css)
        self.assertIn(".vf-command-record--ai", css)
        self.assertIn(".text-red-900", css)
        self.assertIn("color: var(--vf-danger) !important", css)

    def test_phase_does_not_touch_runtime_contracts(self):
        paths = {"01_frontend/visionflow-web/src/app/globals.css", "01_frontend/visionflow-web/src/components/dashboard/operations-dashboard.tsx", "scripts/tests/test_visionflow_system_traceability_command_dashboard.py"}
        self.assertFalse(any(path.startswith(("02_backend/", "03_ai-server/")) or "compose" in path for path in paths))

if __name__ == "__main__":
    unittest.main()
