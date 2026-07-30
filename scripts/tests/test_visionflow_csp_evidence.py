from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIRECTORY))

import visionflow_csp_evidence as evidence  # noqa: E402


def status_fixture(reports: list[dict[str, object]] | None = None) -> dict[str, object]:
    values = reports or []
    return {
        "enabled": True,
        "mode": "REPORT_ONLY",
        "persisted": False,
        "storage": "BOUNDED_PROCESS_MEMORY",
        "maxReportBytes": 16384,
        "maxRetainedReports": 50,
        "startedAt": "2026-07-23T00:00:00Z",
        "totalReports": len(values),
        "retainedReports": len(values),
        "lastReceivedAt": values[0]["receivedAt"] if values else None,
        "byDirective": [],
        "reports": values,
    }


def report_fixture() -> dict[str, object]:
    return {
        "documentUri": "http://localhost:3000/dashboard",
        "blockedUri": "https://example.invalid/script.js",
        "effectiveDirective": "script-src-elem",
        "violatedDirective": "script-src 'self'",
        "disposition": "report",
        "sourceFile": "http://localhost:3000/_next/app.js",
        "lineNumber": 10,
        "columnNumber": 3,
        "statusCode": 200,
        "receivedAt": "2026-07-23T01:00:00Z",
    }


class NormalizeStatusTests(unittest.TestCase):
    def test_accepts_clean_bounded_status(self) -> None:
        normalized = evidence.normalize_status(status_fixture())
        self.assertEqual(0, normalized["totalReports"])
        self.assertEqual([], normalized["reports"])

    def test_derives_directive_counts(self) -> None:
        report = report_fixture()
        normalized = evidence.normalize_status(status_fixture([report, dict(report)]))
        self.assertEqual(
            [{"directive": "script-src-elem", "count": 2}],
            normalized["byDirective"],
        )

    def test_rejects_unsanitized_query_string(self) -> None:
        report = report_fixture()
        report["blockedUri"] = "https://example.invalid/script.js?token=secret"
        with self.assertRaises(evidence.EvidenceError):
            evidence.normalize_status(status_fixture([report]))

    def test_rejects_unbounded_storage(self) -> None:
        fixture = status_fixture()
        fixture["storage"] = "DATABASE"
        with self.assertRaises(evidence.EvidenceError):
            evidence.normalize_status(fixture)


class EvidenceOutputTests(unittest.TestCase):
    def test_writes_json_csv_html_and_checksums(self) -> None:
        normalized = evidence.normalize_status(status_fixture([report_fixture()]))
        with tempfile.TemporaryDirectory() as directory:
            paths = evidence.write_evidence(
                normalized,
                Path(directory),
                evidence.DEFAULT_URL,
                datetime(2026, 7, 23, 1, 2, 3, tzinfo=timezone.utc),
            )
            for path in paths.values():
                self.assertTrue(path.is_file())
            payload = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual("CSP_OBSERVATION_REVIEW_REQUIRED", payload["status"])
            self.assertIn("script-src-elem", paths["csv"].read_text(encoding="utf-8"))
            checksum_lines = paths["sha256"].read_text(encoding="utf-8").splitlines()
            self.assertEqual(3, len(checksum_lines))

    def test_csv_prefixes_formula_like_values(self) -> None:
        self.assertEqual("'=SUM(A1:A2)", evidence.csv_safe("=SUM(A1:A2)"))


if __name__ == "__main__":
    unittest.main()
