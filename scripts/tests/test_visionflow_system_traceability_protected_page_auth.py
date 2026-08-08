from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class SystemTraceabilityProtectedPageAuthTest(unittest.TestCase):
    def test_shared_server_guard_preserves_security_modes(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/lib/server/protected-page.ts"
        )

        for contract in (
            'getOperatorAuthMode() !== "session"',
            "getOperatorSecurityStatus()",
            "status?.enabled === true",
            "status.authenticated === false",
            'candidate.startsWith("/")',
            '!candidate.startsWith("//")',
            '"/dashboard"',
            "encodeURIComponent(safeReturnTo(returnTo))",
            "buildProtectedReturnTo(",
            "new URLSearchParams()",
            "redirect(",
        ):
            self.assertIn(contract, source)

    def test_protected_pages_use_shared_authentication_guard(self) -> None:
        static_pages = {
            "01_frontend/visionflow-web/src/app/events/page.tsx": "/events",
            "01_frontend/visionflow-web/src/app/statistics/page.tsx": "/statistics",
            "01_frontend/visionflow-web/src/app/models/page.tsx": "/models",
        }

        for path, return_to in static_pages.items():
            with self.subTest(path=path):
                source = read_text(path)
                self.assertIn(
                    'import { requireOperatorAuthentication } '
                    'from "@/lib/server/protected-page";',
                    source,
                )
                self.assertIn(
                    f'await requireOperatorAuthentication("{return_to}");',
                    source,
                )

        query_pages = {
            "01_frontend/visionflow-web/src/app/maintenance/page.tsx": "/maintenance",
            "01_frontend/visionflow-web/src/app/audit-logs/page.tsx": "/audit-logs",
        }
        for path, return_to in query_pages.items():
            with self.subTest(path=path):
                source = read_text(path)
                self.assertIn("buildProtectedReturnTo", source)
                self.assertIn("requireOperatorAuthentication", source)
                self.assertIn(
                    f'buildProtectedReturnTo("{return_to}",',
                    source,
                )

    def test_ci_runs_when_protected_page_auth_changes(self) -> None:
        workflow = read_text(".github/workflows/api-audit.yml")

        for path in (
            '"01_frontend/visionflow-web/src/app/audit-logs/**"',
            '"01_frontend/visionflow-web/src/app/maintenance/**"',
        ):
            self.assertGreaterEqual(workflow.count(path), 2)

        self.assertIn(
            '-p "test_visionflow_system_traceability_*.py"',
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
