from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class SystemTraceabilityOperatorSecuritySurfacesTest(unittest.TestCase):
    def test_browser_realtime_logs_never_include_raw_operational_payloads(self) -> None:
        hooks = (
            "01_frontend/visionflow-web/src/hooks/use-drone-fleet-telemetry.ts",
            "01_frontend/visionflow-web/src/hooks/use-incident-realtime.ts",
            "01_frontend/visionflow-web/src/hooks/use-ai-alert-realtime.ts",
        )

        for hook in hooks:
            with self.subTest(hook=hook):
                source = read_text(hook)
                self.assertNotIn("console.table(", source)
                self.assertNotRegex(
                    source,
                    r"console\.(?:log|error|warn)\(\s*[\"'][^\"']*[\"']"
                    r"\s*,\s*(?:message\.body|incomingDrone|incomingEvent|frame)",
                )

    def test_public_actuator_health_does_not_disclose_component_details(self) -> None:
        application = read_text(
            "02_backend/visionflow-api/src/main/resources/application.yml"
        )
        security = read_text(
            "02_backend/visionflow-api/src/main/java/com/visionflow/api/common/config/SecurityConfig.java"
        )

        self.assertIn("show-details: never", application)
        self.assertNotIn("show-details: always", application)
        self.assertIn('"/actuator/health"', security)
        self.assertIn(".permitAll()", security)

    def test_authenticated_audit_actor_takes_precedence_over_request_actor(self) -> None:
        source = read_text(
            "02_backend/visionflow-api/src/main/java/com/visionflow/api/audit/service/AuditLogService.java"
        )
        start = source.index("private RequestAuditContext resolveRequestContext(")
        end = source.index("private String authenticatedActor()", start)
        resolver = source[start:end]

        self.assertLess(
            resolver.index("String actorCandidate = authenticatedActor();"),
            resolver.index("if (actorCandidate == null && trustedActorOverride)"),
        )
        self.assertIn("if (actorCandidate == null && !credentialRegistry.isEnabled())", resolver)
        self.assertIn("actorCandidate = explicitActor;", resolver)

    def test_same_origin_guard_fails_closed_when_browser_context_headers_are_missing(
        self,
    ) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/lib/server/same-origin.ts"
        )

        self.assertIn(
            'request.headers.get("sec-fetch-site") === "same-origin"',
            source,
        )
        self.assertRegex(
            source,
            re.compile(r'if \(origin === null\)\s*\{\s*return false;\s*\}'),
        )

    def test_local_mysql_port_is_bound_to_loopback_by_default(self) -> None:
        compose = read_text("compose.yaml")

        self.assertIn(
            '"${MYSQL_BIND_IP:-127.0.0.1}:${MYSQL_HOST_PORT:-3307}:3306"',
            compose,
        )
        self.assertNotIn('"${MYSQL_HOST_PORT:-3307}:3306"', compose)

    def test_bff_defaults_to_session_auth_and_never_injects_static_operator_key(
        self,
    ) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/lib/server/operator-auth.ts"
        )
        mode_function = source[
            source.index("export function getOperatorAuthMode()"):
            source.index("export async function withBackendOperatorAuth(")
        ]
        auth_function = source[
            source.index("export async function withBackendOperatorAuth("):
        ]

        self.assertIn('=== "static"', mode_function)
        self.assertIn(': "session"', mode_function)
        self.assertIn("headers.delete(OPERATOR_KEY_HEADER)", auth_function)
        self.assertIn(
            "headers.set(OPERATOR_SESSION_HEADER, operatorSession)",
            auth_function,
        )
        self.assertNotIn("VISIONFLOW_WEB_OPERATOR_KEY", auth_function)
        self.assertNotIn("VISIONFLOW_OPERATOR_KEY", auth_function)

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
        self.assertIn('import { readBoundedRequestBody }', source)
        self.assertIn('readBoundedRequestBody(request.body, MAX_REPORT_BYTES)', post_branch)
        self.assertIn('request.headers.get("content-length")', post_branch)
        self.assertNotIn('request.text()', post_branch)
        self.assertIn('"INVALID_CONTENT_LENGTH"', post_branch)
        self.assertIn("retainReport(sanitizedReport)", post_branch)
        self.assertIn("status: 204", post_branch)

    def test_pairing_proxy_bounds_request_and_backend_response_bodies(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/lib/server/operator-pairing.ts"
        )

        for contract in (
            "MAX_PAIRING_REQUEST_BYTES = 8 * 1024",
            "MAX_PAIRING_RESPONSE_BYTES = 16 * 1024",
            "readBoundedRequestBody(",
            "request.body",
            "response.body",
            'status: 413',
            'status: 502',
        ):
            self.assertIn(contract, source)

        self.assertNotIn("request.text()", source)
        self.assertNotIn("response.text()", source)

    def test_operator_login_and_password_change_parse_bounded_json(self) -> None:
        login = read_text(
            "01_frontend/visionflow-web/src/app/api/operator/session/route.ts"
        )
        password = read_text(
            "01_frontend/visionflow-web/src/app/api/operator/password/route.ts"
        )

        self.assertIn("readBoundedJsonRequest(request, 12 * 1024)", login)
        self.assertIn("readBoundedJsonRequest(request, 4 * 1024)", password)
        self.assertNotIn("request.json()", login)
        self.assertNotIn("request.json()", password)

    def test_incident_maintenance_and_ai_alert_writes_bound_request_streams(self) -> None:
        routes = (
            "01_frontend/visionflow-web/src/app/api/incidents/[id]/status/route.ts",
            "01_frontend/visionflow-web/src/app/api/incidents/[id]/assignee/route.ts",
            "01_frontend/visionflow-web/src/app/api/incidents/[id]/priority/route.ts",
            "01_frontend/visionflow-web/src/app/api/incidents/[id]/notes/route.ts",
            "01_frontend/visionflow-web/src/app/api/maintenance/work-orders/[id]/start/route.ts",
            "01_frontend/visionflow-web/src/app/api/maintenance/work-orders/[id]/complete/route.ts",
            "01_frontend/visionflow-web/src/app/api/ai/alerts/[id]/acknowledge/route.ts",
            "01_frontend/visionflow-web/src/app/api/ai/alerts/[id]/resolve/route.ts",
        )

        for route in routes:
            with self.subTest(route=route):
                source = read_text(route)
                self.assertIn("readBoundedMutationText(request,", source)
                self.assertIn("parsedBody.body", source)
                self.assertNotIn("request.text()", source)

    def test_drone_demo_and_geofence_mutations_bound_request_streams(self) -> None:
        cases = {
            "01_frontend/visionflow-web/src/app/api/drones/route.ts": (
                "readBoundedMutationJson(request, 16 * 1024",
            ),
            "01_frontend/visionflow-web/src/app/api/drones/[id]/route.ts": (
                "readBoundedMutationJson(request, 16 * 1024",
                "isValidDroneId(id)",
            ),
            "01_frontend/visionflow-web/src/app/api/drones/[id]/status/route.ts": (
                "readBoundedMutationJson(request, 8 * 1024",
                'code: "INVALID_DRONE_ID"',
            ),
            "01_frontend/visionflow-web/src/app/api/drones/[id]/telemetry/route.ts": (
                "readBoundedMutationText(request, 64 * 1024",
                "readBoundedRequestBody(response.body, 64 * 1024)",
            ),
            "01_frontend/visionflow-web/src/app/api/demo/scenarios/route.ts": (
                "readBoundedMutationJson(request, 4 * 1024",
            ),
            "01_frontend/visionflow-web/src/app/api/geofences/[id]/active/route.ts": (
                "readBoundedMutationText(request, 8 * 1024",
            ),
            "01_frontend/visionflow-web/src/app/api/geofences/route.ts": (
                "readBoundedTextRequest(request, MAX_GEOFENCE_REQUEST_BYTES)",
                "MAX_GEOFENCE_REQUEST_BYTES = 1024 * 1024",
            ),
            "01_frontend/visionflow-web/src/app/api/geofences/[id]/route.ts": (
                "readBoundedTextRequest(request, MAX_GEOFENCE_REQUEST_BYTES)",
                "MAX_GEOFENCE_REQUEST_BYTES = 1024 * 1024",
            ),
        }

        for path, contracts in cases.items():
            with self.subTest(path=path):
                source = read_text(path)
                for contract in contracts:
                    self.assertIn(contract, source)


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
