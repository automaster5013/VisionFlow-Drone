from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class SystemTraceabilityCameraAiAccessTest(unittest.TestCase):
    def test_shared_api_guard_enforces_authentication_and_operator_roles(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/lib/server/operator-api-access.ts"
        )

        for contract in (
            'export type OperatorApiAccessRequirement = "AUTHENTICATED" | "OPERATOR"',
            "getOperatorSecurityStatus()",
            '"OPERATOR_SECURITY_UNAVAILABLE"',
            '"OPERATOR_AUTHENTICATION_REQUIRED"',
            '"OPERATOR_PERMISSION_DENIED"',
            'operator.role !== "OPERATOR"',
            'operator.role !== "ADMIN"',
            '"Cache-Control": "no-store"',
        ):
            self.assertIn(contract, source)

    def test_frame_ingest_checks_origin_and_operator_before_payload(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/app/api/ai/ingest/frame/route.ts"
        )

        for contract in (
            "isSameOriginRequest(request)",
            '"CROSS_ORIGIN_AI_FRAME_INGEST_DENIED"',
            'requireOperatorApiAccess("OPERATOR")',
            "request.arrayBuffer()",
        ):
            self.assertIn(contract, source)

        self.assertLess(
            source.index("isSameOriginRequest(request)"),
            source.index('requireOperatorApiAccess("OPERATOR")'),
        )
        self.assertLess(
            source.index('requireOperatorApiAccess("OPERATOR")'),
            source.index("request.arrayBuffer()"),
        )

    def test_ai_read_proxies_require_authenticated_operator(self) -> None:
        routes = (
            "01_frontend/visionflow-web/src/app/api/ai/ingest/status/route.ts",
            "01_frontend/visionflow-web/src/app/api/ai/metrics/status/route.ts",
            "01_frontend/visionflow-web/src/app/api/ai/stream/status/route.ts",
            "01_frontend/visionflow-web/src/app/api/ai/stream/annotated/route.ts",
        )

        for route in routes:
            with self.subTest(route=route):
                source = read_text(route)
                self.assertIn(
                    'requireOperatorApiAccess("AUTHENTICATED")',
                    source,
                )
                self.assertLess(
                    source.index('requireOperatorApiAccess("AUTHENTICATED")'),
                    source.index("withAiInternalAuth("),
                )

    def test_camera_and_preview_pages_have_server_access_guards(self) -> None:
        pages = {
            "01_frontend/visionflow-web/src/app/cameras/page.tsx": (
                "/cameras",
                "OPERATOR",
            ),
            "01_frontend/visionflow-web/src/app/mobile-camera/page.tsx": (
                "/mobile-camera",
                "OPERATOR",
            ),
            "01_frontend/visionflow-web/src/app/ai-preview/page.tsx": (
                "/ai-preview",
                "AUTHENTICATED",
            ),
        }

        for path, (return_to, requirement) in pages.items():
            with self.subTest(path=path):
                source = read_text(path)
                self.assertIn("requireOperatorPageAccess", source)
                self.assertRegex(
                    source,
                    re.compile(
                        rf'requireOperatorPageAccess\(\s*'
                        rf'"{re.escape(return_to)}",\s*'
                        rf'"{re.escape(requirement)}",?\s*\)',
                    ),
                )
                self.assertIn("<OperatorAccessDenied", source)

    def test_camera_navigation_is_hidden_without_operator_role(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/components/layout/navigation-items.ts"
        )

        for contract in (
            'export type AppNavigationAccess =',
            'access?: AppNavigationAccess',
            'access: "OPERATOR"',
            "hasNavigationAccess",
            'operatorSecurity.role === "OPERATOR"',
            'operatorSecurity.role === "ADMIN"',
        ):
            self.assertIn(contract, source)

    def test_ci_covers_camera_ai_access_boundaries(self) -> None:
        workflow = read_text(".github/workflows/api-audit.yml")

        for path in (
            '"01_frontend/visionflow-web/src/app/ai-preview/**"',
            '"01_frontend/visionflow-web/src/app/cameras/**"',
            '"01_frontend/visionflow-web/src/app/mobile-camera/**"',
            '"01_frontend/visionflow-web/src/components/security/**"',
        ):
            self.assertGreaterEqual(workflow.count(path), 2)

        self.assertIn(
            '-p "test_visionflow_system_traceability_*.py"',
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
