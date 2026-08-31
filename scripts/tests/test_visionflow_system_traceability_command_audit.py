from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "01_frontend" / "visionflow-web" / "src"


def source(relative: str) -> str:
    return (WEB / relative).read_text(encoding="utf-8")


class AuditCommandSurfaceTraceabilityTest(unittest.TestCase):
    def test_audit_page_preserves_protected_query_and_evidence_contract(self) -> None:
        page = source("app/audit-logs/page.tsx")
        for token in (
            "data-audit-command-center",
            "vf-audit-command__hero",
            "vf-audit-command__retention",
            "vf-audit-command__filters",
            "vf-audit-command__records",
            "vf-audit-command__table",
            "requireOperatorAuthentication",
            "getAuditLogs",
            "getAuditRetentionStatus",
            "exportHref(parsed.values)",
            "formatDetails(item.detailsJson)",
        ):
            self.assertIn(token, page)

    def test_audit_export_and_proxy_routes_keep_authorization_guards(self) -> None:
        export_link = source("components/audit/audit-export-link.tsx")
        self.assertIn("useOperatorAccess", export_link)
        self.assertIn("canExportAudit", export_link)
        self.assertIn("vf-audit-command__export", export_link)
        self.assertIn("download", export_link)

        routes = {
            "app/api/audit-logs/route.ts": "proxyAuditRequest",
            "app/api/audit-logs/export/route.ts": "proxyAuditDownload",
            "app/api/audit-logs/retention/route.ts": "proxyAuditRequest",
            "app/api/audit-logs/retention/cleanup/route.ts": "proxyAuditMutationRequest",
        }
        for relative, contract in routes.items():
            self.assertIn(contract, source(relative))
        cleanup = source("app/api/audit-logs/retention/cleanup/route.ts")
        self.assertIn("rejectCrossOriginOperatorMutation", cleanup)
        self.assertIn('get("confirm") !== "true"', cleanup)
        self.assertIn('get("backupConfirmed") !== "true"', cleanup)

    def test_audit_theme_and_responsive_contrast_contract(self) -> None:
        css = source("app/globals.css")
        for token in (
            "/* Phase 1F: audit evidence command surfaces. */",
            ".vf-audit-command__hero",
            ".vf-audit-command__warning",
            '.vf-audit-command__table',
            'html[data-resolved-theme="dark"] .vf-audit-command__warning',
            "@media (max-width: 767px)",
        ):
            self.assertIn(token, css)


if __name__ == "__main__":
    unittest.main()
