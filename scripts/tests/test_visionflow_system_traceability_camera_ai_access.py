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
            'request.headers.get("content-length")',
            "readBoundedRequestBody(request.body, MAX_FRAME_BYTES)",
        ):
            self.assertIn(contract, source)

        self.assertLess(
            source.index("isSameOriginRequest(request)"),
            source.index('requireOperatorApiAccess("OPERATOR")'),
        )
        self.assertLess(
            source.index('requireOperatorApiAccess("OPERATOR")'),
            source.index("readBoundedRequestBody(request.body, MAX_FRAME_BYTES)"),
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

    def test_snapshot_upload_and_download_are_stream_size_bounded(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/app/api/ai/events/[id]/snapshot/route.ts"
        )

        for contract in (
            "MAX_SNAPSHOT_REQUEST_BYTES",
            "MAX_MULTIPART_OVERHEAD_BYTES = 128 * 1024",
            "readBoundedRequestBody(",
            "MAX_SNAPSHOT_REQUEST_BYTES,",
            "new Request(request.url",
            "request.body",
            "response.body",
            "MAX_SNAPSHOT_API_RESPONSE_BYTES",
            "status: 413",
        ):
            self.assertIn(contract, source)

        self.assertNotIn("request.formData()", source)
        self.assertNotIn("response.arrayBuffer()", source)

        application = read_text(
            "02_backend/visionflow-api/src/main/resources/application.yml"
        )
        self.assertRegex(application, r"(?m)^\s+max-file-size: 10MB$")
        self.assertRegex(application, r"(?m)^\s+max-request-size: 11MB$")

    def test_geofence_and_flight_session_mutations_bound_request_streams(self) -> None:
        cases = {
            "01_frontend/visionflow-web/src/app/api/geofences/route.ts": (
                "readBoundedTextRequest(request, MAX_GEOFENCE_REQUEST_BYTES)",
                "MAX_GEOFENCE_REQUEST_BYTES = 1024 * 1024",
            ),
            "01_frontend/visionflow-web/src/app/api/geofences/[id]/route.ts": (
                "readBoundedTextRequest(request, MAX_GEOFENCE_REQUEST_BYTES)",
                "MAX_GEOFENCE_REQUEST_BYTES = 1024 * 1024",
            ),
            "01_frontend/visionflow-web/src/app/api/drones/[id]/flight-sessions/route.ts": (
                "readBoundedTextRequest(request, 2_000)",
                'status: parsedBody.reason === "too_large" ? 413 : 400',
            ),
            "01_frontend/visionflow-web/src/app/api/drones/[id]/flight-sessions/[sessionId]/route.ts": (
                "readBoundedTextRequest(request, 4_000)",
                'status: parsedBody.reason === "too_large" ? 413 : 400',
            ),
        }

        for path, contracts in cases.items():
            with self.subTest(path=path):
                source = read_text(path)
                for contract in contracts:
                    self.assertIn(contract, source)
                self.assertNotIn("request.text()", source)

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
