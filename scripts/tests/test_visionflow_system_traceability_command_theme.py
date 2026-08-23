from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class SystemTraceabilityCommandThemeTest(unittest.TestCase):
    def test_root_layout_bootstraps_theme_before_hydration(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/app/layout.tsx"
        )

        for contract in (
            'import Script from "next/script";',
            "buildThemeBootstrapScript",
            'id="visionflow-theme-bootstrap"',
            'strategy="beforeInteractive"',
            "suppressHydrationWarning",
            'data-theme="system"',
            'data-resolved-theme="light"',
            "<ThemeProvider>",
            'className="vf-app-body min-h-screen antialiased"',
        ):
            self.assertIn(contract, source)

    def test_theme_store_is_hydration_safe_and_browser_local(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/lib/theme.ts"
        )
        provider = read_text(
            "01_frontend/visionflow-web/src/components/theme/theme-provider.tsx"
        )

        for contract in (
            "visionflow.theme-preference.v1",
            "vf-theme",
            "visionflow:theme-change",
            "window.localStorage",
            'window.matchMedia("(prefers-color-scheme: dark)")',
            "root.dataset.theme",
            "root.dataset.resolvedTheme",
            "SameSite=Lax",
            "readThemeSnapshot",
            "getServerThemeSnapshot",
            "subscribeThemeSnapshot",
            'window.addEventListener("storage", handleStorage)',
            'window.addEventListener(THEME_CHANGE_EVENT, handleThemeChange)',
            'media.addEventListener("change", handleMediaChange)',
            "window.dispatchEvent(new Event(THEME_CHANGE_EVENT))",
        ):
            self.assertIn(contract, source)

        for contract in (
            '"use client";',
            "ThemeContext",
            "useSyncExternalStore",
            "subscribeThemeSnapshot",
            "readThemeSnapshot",
            "getServerThemeSnapshot",
            "writeThemePreference",
            "parseThemeSnapshot",
        ):
            self.assertIn(contract, provider)

        self.assertNotIn("useEffect", provider)
        self.assertNotIn("setPreferenceState", provider)
        self.assertNotIn("setResolvedTheme", provider)

    def test_header_exposes_accessible_three_mode_selector_and_clock(self) -> None:
        header = read_text(
            "01_frontend/visionflow-web/src/components/layout/app-header.tsx"
        )
        selector = read_text(
            "01_frontend/visionflow-web/src/components/theme/theme-selector.tsx"
        )
        clock = read_text(
            "01_frontend/visionflow-web/src/components/layout/command-clock.tsx"
        )

        self.assertIn("<ThemeSelector />", header)
        self.assertIn("<CommandClock />", header)
        self.assertIn(
            "<MobileNavigation operatorSecurity={operatorSecurity} />",
            header,
        )

        for contract in (
            'role="group"',
            'aria-label="화면 테마"',
            "aria-pressed={preference === option.value}",
            'value: "system"',
            'value: "light"',
            'value: "dark"',
            'aria-live="polite"',
        ):
            self.assertIn(contract, selector)

        self.assertIn('"use client";', clock)
        self.assertIn("window.setInterval(tick, 1000)", clock)
        self.assertIn('aria-label="현재 로컬 시각"', clock)

    def test_command_shell_tokens_support_day_night_and_reduced_motion(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/app/globals.css"
        )

        for contract in (
            'html[data-resolved-theme="light"]',
            'html[data-resolved-theme="dark"]',
            "--vf-bg:",
            "--vf-surface-1:",
            "--vf-text-primary:",
            "--vf-accent:",
            ".vf-command-header",
            ".vf-command-sidebar",
            ".vf-theme-selector",
            ".vf-sidebar-link.is-active",
            "@media (prefers-reduced-motion: reduce)",
        ):
            self.assertIn(contract, source)

        self.assertNotIn("#000000", source)
        self.assertNotIn("#FFFFFF", source)

    def test_existing_navigation_contract_remains_intact(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/components/layout/app-sidebar.tsx"
        )

        self.assertTrue(source.startswith('"use client";'))
        for contract in (
            "usePathname",
            "isNavigationItemActive",
            'aria-label="주요 메뉴"',
            'aria-current={active ? "page" : undefined}',
            "item.activeAliases",
        ):
            self.assertIn(contract, source)

    def test_ci_runs_theme_contract_on_push_and_pull_request(self) -> None:
        workflow = read_text(".github/workflows/api-audit.yml")

        self.assertGreaterEqual(workflow.count('- "**"'), 2)
        self.assertIn(
            '-p "test_visionflow_system_traceability_*.py"',
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
