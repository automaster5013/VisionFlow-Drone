from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class SystemTraceabilityPublicDashboardModeTest(unittest.TestCase):
    def test_public_mode_uses_only_explicit_public_sources(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/app/dashboard/page.tsx"
        )

        for contract in (
            'getOperatorAuthMode() === "session"',
            "operatorSecurity?.enabled === true",
            "operatorSecurity.authenticated === false",
            'buildProtectedReturnTo("/dashboard", search)',
            "data-public-dashboard-mode",
            "getBackendHealth()",
            "loadMobileEvidenceStatus()",
            "/operator-login?returnTo=",
            "비행 세션, AI 경보, Incident,",
            "함대 신뢰도는 운영자 로그인 후 제공됩니다.",
        ):
            self.assertIn(contract, source)

        public_start = source.index("if (publicMode) {")
        protected_start = source.index(
            "const parsedFilters = parseDashboardFilters(search);"
        )
        self.assertLess(public_start, protected_start)

        public_branch = source[public_start:protected_start]
        for protected_call in (
            "loadOperations(",
            "loadAiAlerts(",
            "loadIncidents(",
            "loadFleetReliability(",
            "<OperationsDashboard",
            "<AiAlertOperationsPanel",
            "<IncidentOperationsPanel",
            "<FleetReliabilityAttentionPanel",
            "<AiAlertRealtimeNotifier",
        ):
            self.assertNotIn(protected_call, public_branch)

    def test_authenticated_mode_preserves_operational_dashboard(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/app/dashboard/page.tsx"
        )
        protected_start = source.index(
            "const parsedFilters = parseDashboardFilters(search);"
        )
        protected_branch = source[protected_start:]

        for contract in (
            "loadOperations(parsedFilters.query",
            "loadAiAlerts(aiAlertQuery",
            "loadIncidents(incidentQuery",
            "loadFleetReliability()",
            "<OperationsDashboard",
            "<FleetReliabilityAttentionPanel",
            "<AiAlertRealtimeNotifier",
            "<IncidentOperationsPanel",
            "<AiAlertOperationsPanel",
            "<HealthDashboard",
        ):
            self.assertIn(contract, protected_branch)

    def test_ci_runs_when_dashboard_access_changes(self) -> None:
        workflow = read_text(".github/workflows/api-audit.yml")
        self.assertGreaterEqual(
            workflow.count(
                '"01_frontend/visionflow-web/src/app/dashboard/**"'
            ),
            2,
        )
        self.assertIn(
            '-p "test_visionflow_system_traceability_*.py"',
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
