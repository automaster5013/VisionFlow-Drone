from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "01_frontend" / "visionflow-web" / "src"


def source(relative: str) -> str:
    return (WEB / relative).read_text(encoding="utf-8")


class SecurityCommandSurfaceTraceabilityTest(unittest.TestCase):
    def test_security_semantic_command_surfaces_are_present(self) -> None:
        page = source("app/security-status/page.tsx")
        header = source("components/security/security-header-probe.tsx")
        csp = source("components/security/csp-report-monitor.tsx")

        for marker in (
            "data-security-command-center",
            "vf-security-command__hero",
            "vf-security-command__status",
            "vf-security-command__deferred",
            "vf-security-command__restricted",
        ):
            self.assertIn(marker, page)

        for component in (header, csp):
            for marker in (
                "vf-security-command__panel",
                "vf-security-command__eyebrow",
                "vf-security-command__section-title",
                "vf-security-command__button",
                "vf-security-command__badge",
            ):
                self.assertIn(marker, component)

        self.assertIn("vf-security-command__check--good", header)
        self.assertIn("vf-security-command__check--danger", header)
        self.assertIn("vf-security-command__metric", csp)
        self.assertIn("vf-security-command__report", csp)

    def test_existing_security_and_admin_boundaries_are_preserved(self) -> None:
        page = source("app/security-status/page.tsx")
        header = source("components/security/security-header-probe.tsx")
        csp = source("components/security/csp-report-monitor.tsx")

        for contract in (
            '"/security-status",',
            '"AUTHENTICATED",',
            "getOperatorSecurityStatus()",
            "loadSessions(canAdminister)",
            "{canAdminister ? (",
            "<CspReportMonitor />",
            "data-admin-security-detail-restricted",
        ):
            self.assertIn(contract, page)

        self.assertIn('fetch("/dashboard"', header)
        self.assertIn('fetch("/api/security/csp-report"', csp)
        self.assertIn('method: "GET"', csp)
        self.assertIn("쿼리 문자열을 제거한 정제 보고서만", csp)

    def test_phase_1i_theme_and_responsive_contract_uses_shared_tokens(self) -> None:
        css = source("app/globals.css")
        for selector in (
            "/* Phase 1I: security posture command surfaces. */",
            ".vf-security-command__status--good",
            ".vf-security-command__status--warning",
            ".vf-security-command__check--good",
            ".vf-security-command__check--danger",
            ".vf-security-command__badge--warning",
            ".vf-security-command__notice--danger",
            'html[data-resolved-theme="dark"] .vf-security-command',
            "@media (max-width: 767px)",
        ):
            self.assertIn(selector, css)

        for token in (
            "var(--vf-surface-1)",
            "var(--vf-surface-2)",
            "var(--vf-surface-3)",
            "var(--vf-border)",
            "var(--vf-text-primary)",
            "var(--vf-text-secondary)",
            "var(--vf-accent)",
        ):
            self.assertIn(token, css)


if __name__ == "__main__":
    unittest.main()
