import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "visionflow_maintenance_acceptance.py"
)
SPEC = importlib.util.spec_from_file_location(
    "visionflow_maintenance_acceptance",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class MaintenanceAcceptanceTests(unittest.TestCase):
    def clearance(self, drone_id=1, work_order_id=7):
        return {
            "droneId": drone_id,
            "mode": "ENFORCED",
            "enforced": True,
            "flightAllowed": False,
            "attentionRequired": True,
            "workOrderId": work_order_id,
            "workOrderStatus": "OPEN",
            "clearanceStatus": "PENDING_INSPECTION",
            "reason": "점검 대기",
        }

    def test_valid_fleet_requires_consistent_counts(self):
        fleet = {
            "mode": "ENFORCED",
            "enforced": True,
            "totalDrones": 1,
            "allowedDrones": 0,
            "attentionDrones": 1,
            "blockedDrones": 1,
            "evaluatedAt": "2026-07-26T00:00:00Z",
            "clearances": [self.clearance()],
        }
        self.assertTrue(MODULE.valid_fleet(fleet))
        fleet["totalDrones"] = 2
        self.assertFalse(MODULE.valid_fleet(fleet))
        fleet["totalDrones"] = 1
        fleet["attentionDrones"] = 0
        self.assertFalse(MODULE.valid_fleet(fleet))

    def test_detail_validation_checks_work_order_and_drone(self):
        detail = {
            "workOrder": {"id": 7, "droneId": 1},
            "history": [
                {
                    "id": 11,
                    "actionType": "CREATED",
                    "actor": "system",
                    "createdAt": "2026-07-26T00:00:00",
                }
            ],
        }
        self.assertTrue(MODULE.valid_detail(detail, 7, 1))
        self.assertFalse(MODULE.valid_detail(detail, 8, 1))

    def metrics(self):
        return {
            "windowDays": 30,
            "windowStartedAt": "2026-06-26T00:00:00Z",
            "generatedAt": "2026-07-26T00:00:00Z",
            "totalWorkOrders": 4,
            "openWorkOrders": 1,
            "inProgressWorkOrders": 1,
            "completedWorkOrders": 1,
            "groundedWorkOrders": 1,
            "resolvedWorkOrders": 2,
            "resolutionRatePercent": 50.0,
            "averageStartDelayMinutes": 60,
            "averageResolutionMinutes": 240,
            "gateMode": "ENFORCED",
            "gateEnforced": True,
            "totalDrones": 3,
            "allowedDrones": 1,
            "attentionDrones": 2,
            "blockedDrones": 2,
        }

    def priority_queue(self):
        return {
            "mode": "ENFORCED",
            "enforced": True,
            "evaluatedAt": "2026-07-26T00:00:00Z",
            "totalDrones": 1,
            "urgentDrones": 1,
            "attentionDrones": 0,
            "normalDrones": 0,
            "overdueDrones": 1,
            "dueSoonDrones": 0,
            "priorities": [
                {
                    "droneId": 1,
                    "priority": "CRITICAL",
                    "riskScore": 100,
                    "flightAllowed": False,
                    "attentionRequired": True,
                    "workOrderId": None,
                    "workOrderStatus": None,
                    "clearanceStatus": None,
                    "openedAt": None,
                    "waitingMinutes": None,
                    "slaStatus": "OVERDUE",
                    "slaDueAt": "2026-07-25T23:00:00Z",
                    "slaRemainingMinutes": 0,
                    "slaOverdueMinutes": 60,
                    "recommendedAction": "SLA 초과: 비행을 중지하세요.",
                    "reason": "점검 대기",
                }
            ],
        }

    def sla_automation(self):
        return {
            "automationEnabled": True,
            "openSlaMinutes": 120,
            "inProgressSlaMinutes": 240,
            "dueSoonMinutes": 30,
            "initialDelayMs": 15000,
            "scanDelayMs": 30000,
        }

    def test_valid_metrics_requires_consistent_work_order_and_fleet_totals(self):
        metrics = self.metrics()

        self.assertTrue(MODULE.valid_metrics(metrics, 30))
        metrics["totalWorkOrders"] = 5
        self.assertFalse(MODULE.valid_metrics(metrics, 30))
        metrics["totalWorkOrders"] = 4
        metrics["allowedDrones"] = 2
        self.assertFalse(MODULE.valid_metrics(metrics, 30))

    def test_metrics_signature_ignores_generated_timestamps(self):
        backend = self.metrics()
        frontend = dict(backend)
        frontend["generatedAt"] = "2026-07-26T00:00:01Z"
        frontend["windowStartedAt"] = "2026-06-26T00:00:01Z"

        self.assertEqual(
            MODULE.metrics_signature(backend),
            MODULE.metrics_signature(frontend),
        )

    def test_metrics_must_match_current_fleet_gate(self):
        metrics = self.metrics()
        fleet = {
            "mode": "ENFORCED",
            "enforced": True,
            "totalDrones": 3,
            "allowedDrones": 1,
            "attentionDrones": 2,
            "blockedDrones": 2,
        }

        self.assertTrue(MODULE.metrics_matches_fleet(metrics, fleet))
        fleet["blockedDrones"] = 1
        self.assertFalse(MODULE.metrics_matches_fleet(metrics, fleet))

    def test_priority_queue_requires_sorted_consistent_counts(self):
        priority_queue = self.priority_queue()

        self.assertTrue(MODULE.valid_priority_queue(priority_queue))
        priority_queue["urgentDrones"] = 0
        self.assertFalse(MODULE.valid_priority_queue(priority_queue))
        priority_queue["urgentDrones"] = 1
        priority_queue["overdueDrones"] = 0
        self.assertFalse(MODULE.valid_priority_queue(priority_queue))

    def test_priority_queue_must_match_current_fleet(self):
        priority_queue = self.priority_queue()
        fleet = {
            "mode": "ENFORCED",
            "enforced": True,
            "totalDrones": 1,
            "clearances": [self.clearance(work_order_id=None)],
        }

        self.assertTrue(
            MODULE.priority_matches_fleet(priority_queue, fleet)
        )
        priority_queue["priorities"][0]["droneId"] = 2
        self.assertFalse(
            MODULE.priority_matches_fleet(priority_queue, fleet)
        )

    def test_server_render_accepts_loading_and_hydrated_kpi_markers(self):
        self.assertTrue(
            MODULE.has_maintenance_kpi_content(
                "정비 운영 KPI를 집계하고 있습니다."
            )
        )
        self.assertTrue(
            MODULE.has_maintenance_kpi_content(
                "<h2>정비 운영 현황</h2>"
            )
        )
        self.assertFalse(
            MODULE.has_maintenance_kpi_content(
                "<main>기체 점검 작업지시</main>"
            )
        )
        self.assertTrue(
            MODULE.has_maintenance_priority_content(
                "드론별 정비 우선순위를 계산하고 있습니다."
            )
        )
        self.assertFalse(
            MODULE.has_maintenance_priority_content(
                "<main>기체 점검 작업지시</main>"
            )
        )
        self.assertTrue(
            MODULE.has_team_copyright(
                "© 2026 Team PyvaOps. All rights reserved."
            )
        )
        self.assertFalse(
            MODULE.has_team_copyright(
                "© 2026 Team PyvaOps."
            )
        )
        self.assertTrue(
            MODULE.has_sla_automation_content(
                '<div data-maintenance-sla-automation>SLA 자동화</div>'
            )
        )

    def test_sla_automation_requires_valid_positive_policy(self):
        status = self.sla_automation()
        self.assertTrue(MODULE.valid_sla_automation(status))
        status["scanDelayMs"] = 0
        self.assertFalse(MODULE.valid_sla_automation(status))
        status["scanDelayMs"] = 30000
        status["dueSoonMinutes"] = 121
        self.assertFalse(MODULE.valid_sla_automation(status))
        status["dueSoonMinutes"] = 30
        status["automationEnabled"] = False
        self.assertFalse(MODULE.valid_sla_automation(status))

    def test_main_records_kpi_proxy_validation_and_page_content(self):
        clearance = self.clearance(work_order_id=None)
        fleet = {
            "mode": "ENFORCED",
            "enforced": True,
            "totalDrones": 1,
            "allowedDrones": 0,
            "attentionDrones": 1,
            "blockedDrones": 1,
            "evaluatedAt": "2026-07-26T00:00:00Z",
            "clearances": [clearance],
        }
        metrics = self.metrics()
        metrics.update(
            {
                "totalDrones": 1,
                "allowedDrones": 0,
                "attentionDrones": 1,
                "blockedDrones": 1,
            }
        )
        priority_queue = self.priority_queue()
        sla_automation = self.sla_automation()

        def response(status, body):
            return MODULE.HttpResult(
                status,
                body if isinstance(body, str) else json.dumps(body),
                1,
                None,
            )

        def fake_request(uri, _timeout):
            if uri.endswith("/api/health"):
                return response(200, {"status": "UP"})
            if uri.endswith(
                "/api/maintenance/metrics?windowDays=0"
            ):
                return response(400, {"code": "INVALID_ARGUMENT"})
            if uri.endswith(
                "/api/maintenance/metrics?windowDays=30"
            ):
                return response(200, metrics)
            if uri.endswith("/api/maintenance/priorities"):
                return response(200, priority_queue)
            if uri.endswith("/api/maintenance/sla"):
                return response(200, sla_automation)
            if uri.endswith("/api/maintenance/flight-clearance/1"):
                return response(200, clearance)
            if uri.endswith("/api/maintenance/flight-clearance"):
                return response(200, fleet)
            if uri.endswith("/maintenance"):
                return response(
                    200,
                    "<html>정비 운영 KPI를 집계하고 있습니다."
                    "드론별 정비 우선순위를 계산하고 있습니다."
                    "SLA 자동 Incident 상향"
                    "© 2026 Team PyvaOps. All rights reserved.</html>",
                )
            if uri.endswith(("/drones", "/demo-scenario")):
                return response(200, "<html>OK</html>")
            raise AssertionError(f"Unexpected URI: {uri}")

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(MODULE, "request", side_effect=fake_request):
                exit_code = MODULE.main(
                    [
                        "--output-directory",
                        directory,
                    ]
                )
            reports = list(Path(directory).glob("*.json"))
            self.assertEqual(0, exit_code)
            self.assertEqual(1, len(reports))
            report = json.loads(reports[0].read_text(encoding="utf-8"))
            by_key = {
                item["key"]: item["status"]
                for item in report["checks"]
            }
            for key in (
                "backend-maintenance-metrics",
                "frontend-maintenance-metrics-proxy",
                "backend-maintenance-metrics-window-validation",
                "frontend-maintenance-metrics-window-validation",
                "frontend-maintenance-kpi-content",
                "backend-maintenance-priorities",
                "frontend-maintenance-priorities-proxy",
                "frontend-maintenance-priority-content",
                "frontend-team-copyright",
                "backend-maintenance-sla-automation",
                "frontend-maintenance-sla-automation-proxy",
                "frontend-maintenance-sla-automation-content",
            ):
                self.assertEqual("PASS", by_key[key])

    def test_report_json_preserves_korean_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(
                json.dumps(
                    {"detail": "재운항 승인"},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.assertIn("재운항 승인", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
