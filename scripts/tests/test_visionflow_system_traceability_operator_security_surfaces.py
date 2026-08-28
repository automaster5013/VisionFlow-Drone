from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class SystemTraceabilityOperatorSecuritySurfacesTest(unittest.TestCase):
    def test_settings_page_requires_authenticated_operator(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/app/settings/page.tsx"
        )

        self.assertIn(
            'import { OperatorAccessDenied } '
            'from "@/components/security/operator-access-denied";',
            source,
        )
        self.assertIn(
            'import { requireOperatorPageAccess } '
            'from "@/lib/server/protected-page";',
            source,
        )
        self.assertRegex(
            source,
            re.compile(
                r'requireOperatorPageAccess\(\s*'
                r'"/settings",\s*"AUTHENTICATED",?\s*\)',
            ),
        )
        self.assertIn("<OperatorAccessDenied", source)
        self.assertIn("<OperatorConsoleSettingsCenter />", source)
        self.assertLess(
            source.index("requireOperatorPageAccess("),
            source.index("<OperatorConsoleSettingsCenter />"),
        )

    def test_security_status_page_requires_auth_before_loading_status(
        self,
    ) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/app/security-status/page.tsx"
        )

        self.assertRegex(
            source,
            re.compile(
                r'requireOperatorPageAccess\(\s*'
                r'"/security-status",\s*"AUTHENTICATED",?\s*\)',
            ),
        )
        self.assertIn("<OperatorAccessDenied", source)
        self.assertLess(
            source.index("requireOperatorPageAccess("),
            source.index("getOperatorSecurityStatus()"),
        )

    def test_navigation_hides_settings_and_security_status_until_login(
        self,
    ) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/components/layout/navigation-items.ts"
        )

        for label, href in (
            ("보안 상태", "/security-status"),
            ("설정", "/settings"),
        ):
            with self.subTest(label=label):
                self.assertRegex(
                    source,
                    re.compile(
                        r"\{\s*"
                        rf'label:\s*"{re.escape(label)}",\s*'
                        rf'href:\s*"{re.escape(href)}",\s*'
                        r'access:\s*"AUTHENTICATED",?\s*'
                        r"\}",
                    ),
                )

    def test_shared_api_guard_supports_admin_only_access(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/lib/server/operator-api-access.ts"
        )

        for contract in (
            '"AUTHENTICATED" | "OPERATOR" | "ADMIN"',
            'requirement === "ADMIN"',
            'operator.role !== "ADMIN"',
            '"OPERATOR_ADMIN_REQUIRED"',
            '"이 작업에는 ADMIN 권한이 필요합니다."',
        ):
            self.assertIn(contract, source)

    def test_csp_report_get_is_admin_only_while_post_remains_public(
        self,
    ) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/app/api/security/csp-report/route.ts"
        )
        get_start = source.index("export async function GET()")
        post_start = source.index("export async function POST(")
        get_branch = source[get_start:post_start]
        post_branch = source[post_start:]

        self.assertIn('requireOperatorApiAccess("ADMIN")', get_branch)
        self.assertLess(
            get_branch.index('requireOperatorApiAccess("ADMIN")'),
            get_branch.index("getReportStore()"),
        )
        self.assertNotIn("requireOperatorApiAccess(", post_branch)
        self.assertIn("retainReport(sanitizedReport)", post_branch)
        self.assertIn("status: 204", post_branch)

    def test_non_admin_security_page_hides_detailed_observability(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/app/security-status/page.tsx"
        )
        render = source[source.index("return ("):]

        for contract in (
            "{canAdminister ? (",
            "<CspReportMonitor />",
            "data-admin-security-detail-restricted",
            "상세 보안 관찰 정보는 ADMIN 전용입니다.",
            "CSP 위반 URI·source file",
            "loadSessions(canAdminister)",
        ):
            self.assertIn(contract, source)

        self.assertLess(
            render.index("{canAdminister ? ("),
            render.index("<CspReportMonitor />"),
        )
        self.assertLess(
            render.index("<CspReportMonitor />"),
            render.index("data-admin-security-detail-restricted"),
        )

    def test_ci_tracks_security_status_access_boundary(self) -> None:
        workflow = read_text(".github/workflows/api-audit.yml")

        self.assertGreaterEqual(
            workflow.count(
                '"01_frontend/visionflow-web/src/app/security-status/**"'
            ),
            2,
        )
        self.assertIn(
            '-p "test_visionflow_system_traceability_*.py"',
            workflow,
        )


    def test_mobile_https_refresh_waits_for_new_fresh_agent_profile(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/components/security/"
            "operator-pairing-console.tsx"
        )

        for contract in (
            "MOBILE_RUNTIME_REFRESH_ATTEMPTS = 8",
            "waitForNextRuntimeProbe",
            "previousGeneratedAt",
            "latestProfile?.fresh && latestProfile.origin && generatedAgain",
            'setMobileOrigin("")',
            "!runtimeProfile?.fresh",
        ):
            self.assertIn(contract, source)

        self.assertIn(
            "`/api/mobile/runtime-network?refresh=${Date.now()}`",
            source,
        )

    def test_mobile_runtime_loader_uses_static_container_runtime_file(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/lib/server/"
            "mobile-https-runtime.ts"
        )

        for contract in (
            "const RUNTIME_FILE = path.join(",
            "/*turbopackIgnore: true*/ process.cwd()",
            '"mobile-https-runtime"',
            "lstat(RUNTIME_FILE)",
        ):
            self.assertIn(contract, source)

        self.assertNotIn("VISIONFLOW_MOBILE_HTTPS_RUNTIME_FILE", source)
        self.assertNotIn("runtimeFileCandidates", source)
        self.assertNotIn("path.resolve(", source)

    def test_local_start_includes_mobile_https_and_runtime_agent(self) -> None:
        source = read_text(
            "scripts/local-runtime/start-visionflow-local.ps1"
        )

        for contract in (
            '"visionflow-mobile-https"',
            "Wait-MobileRuntimeProfile",
            "start-mobile-https-runtime-agent.bat",
            "MOBILE_RUNTIME_AGENT=FRESH",
            "MOBILE_RUNTIME_ORIGIN=",
        ):
            self.assertIn(contract, source)


if __name__ == "__main__":
    unittest.main()
