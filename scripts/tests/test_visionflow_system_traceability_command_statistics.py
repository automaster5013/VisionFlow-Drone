from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "01_frontend" / "visionflow-web" / "src"


def source(relative: str) -> str:
    return (WEB / relative).read_text(encoding="utf-8")


class StatisticsCommandSurfaceTraceabilityTest(unittest.TestCase):
    def test_statistics_semantic_command_surfaces_are_present(self) -> None:
        center = source("components/statistics/operations-statistics-center.tsx")
        for marker in (
            "data-statistics-command-center",
            "vf-statistics-command__hero",
            "vf-statistics-command__summary",
            "vf-statistics-command__kpi",
            "vf-statistics-command__health-dock",
            "vf-statistics-command__panel",
            "vf-statistics-command__distribution",
            "vf-statistics-command__drone",
            "vf-statistics-command__gate-grid",
        ):
            self.assertIn(marker, center)

    def test_existing_read_only_statistics_runtime_contract_is_preserved(self) -> None:
        page = source("app/statistics/page.tsx")
        center = source("components/statistics/operations-statistics-center.tsx")

        self.assertIn('requireOperatorAuthentication("/statistics")', page)
        self.assertIn('export const dynamic = "force-dynamic"', page)
        for endpoint in (
            "/api/dashboard/operations?limit=20&from=",
            "/api/flight-quality/fleet-reliability?limitPerDrone=20",
            "/api/maintenance/metrics?windowDays=",
            "/api/ai/metrics/status",
        ):
            self.assertIn(endpoint, center)

        for contract in (
            "Promise.allSettled",
            "AbortController",
            "AUTO_REFRESH_INTERVAL_MS = 30_000",
            "readOperatorConsolePreferences",
            'document.visibilityState === "visible"',
        ):
            self.assertIn(contract, center)

    def test_phase_1g_theme_and_responsive_contract_uses_shared_tokens(self) -> None:
        css = source("app/globals.css")
        for selector in (
            "/* Phase 1G: operations statistics command surfaces. */",
            ".vf-statistics-command__hero",
            ".vf-statistics-command__summary",
            ".vf-statistics-command__panel",
            ".vf-statistics-command__health-chip--degraded",
            ".vf-statistics-command__gate--blocked",
            "@media (max-width: 767px)",
            "/* Phase 1G repair: preserve dark text on the luminous selected range pill. */",
            'html[data-resolved-theme="dark"] .vf-statistics-command .vf-statistics-command__range-button--active',
        ):
            self.assertIn(selector, css)

        for token in (
            "var(--vf-surface-1)",
            "var(--vf-surface-2)",
            "var(--vf-border)",
            "var(--vf-text-primary)",
            "var(--vf-text-secondary)",
            "var(--vf-accent)",
        ):
            self.assertIn(token, css)


if __name__ == "__main__":
    unittest.main()
