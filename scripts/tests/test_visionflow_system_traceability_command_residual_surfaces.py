import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "01_frontend" / "visionflow-web" / "src"
CSS = WEB / "app" / "globals.css"


class ResidualCommandSurfacesTest(unittest.TestCase):
    def test_surface_hooks(self):
        contracts = {
            "components/settings/operator-console-settings-center.tsx":
                ("data-settings-command", "vf-settings-command__hero"),
            "app/operator-sessions/page.tsx":
                ("data-operator-sessions-command", "vf-session-command__hero"),
            "components/security/operator-session-management-panel.tsx":
                ("data-operator-session-panel", "vf-session-command__panel"),
            "app/demo-mode/page.tsx":
                ("data-demo-mode-command", "max-w-[1500px]"),
            "components/demo/demo-mode-console.tsx":
                ("vf-demo-mode-command__hero", "vf-demo-mode-command__mode-action"),
            "components/demo/demo-scenario-console.tsx":
                ("data-demo-scenario-command", "vf-demo-scenario-command__hero"),
        }
        for relative, tokens in contracts.items():
            source = (WEB / relative).read_text(encoding="utf-8")
            for token in tokens:
                self.assertIn(token, source, f"{relative}: {token}")

    def test_demo_mode_aligns_with_shared_shell_content_grid(self):
        page = (WEB / "app" / "demo-mode" / "page.tsx").read_text(
            encoding="utf-8"
        )
        layout = (WEB / "app" / "layout.tsx").read_text(encoding="utf-8")

        self.assertIn(
            '<main className="vf-command-main flex-1 p-4 sm:p-6 xl:p-7">',
            layout,
        )
        self.assertIn("data-demo-mode-command", page)
        self.assertIn(
            'className="vf-demo-mode-command min-h-full"',
            page,
        )
        self.assertIn('className="mx-auto max-w-[1500px]"', page)
        self.assertNotIn("min-h-screen", page)
        self.assertNotIn("px-4 py-6", page)
        self.assertNotIn("sm:px-6", page)
        self.assertNotIn("lg:px-8", page)
        self.assertNotIn("<main", page)

    def test_css_contract(self):
        css = CSS.read_text(encoding="utf-8")
        tokens = (
            "Phase 1K: residual settings command hierarchy",
            "Phase 1K: operator session table contrast",
            "Phase 1K: demo mode command hierarchy",
            "Phase 1K: demo scenario adaptive panels",
            ".vf-session-command__panel button.text-red-700:disabled",
            ".vf-demo-mode-command__mode-action.bg-amber-600:disabled",
            ".vf-demo-scenario-command .bg-slate-900",
        )
        for token in tokens:
            self.assertIn(token, css, token)

    def test_css_is_ui_only(self):
        css = CSS.read_text(encoding="utf-8")
        phase = css.split("/* Phase 1K: residual settings command hierarchy. */", 1)[1]
        phase = phase.split("/* Phase 1A bridge:", 1)[0]
        for token in ("/api/", "fetch(", "Authorization", "VISIONFLOW_"):
            self.assertNotIn(token, phase, token)


if __name__ == "__main__":
    unittest.main()
