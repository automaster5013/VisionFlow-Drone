from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class SystemTraceabilityShellNavigationTest(unittest.TestCase):
    def test_shared_navigation_inventory_preserves_routes_and_admin_gate(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/components/layout/navigation-items.ts"
        )

        for route in (
            "/dashboard",
            "/drones",
            "/cameras",
            "/events",
            "/audit-logs",
            "/security-status",
            "/operator-sessions",
            "/statistics",
            "/models",
            "/settings",
            "/demo-mode",
        ):
            self.assertIn(f'href: "{route}"', source)

        self.assertIn("adminOnly: true", source)
        self.assertIn('activeAliases: ["/mobile-camera"]', source)
        self.assertIn('operatorSecurity.role === "ADMIN"', source)
        self.assertIn("getVisibleNavigationItems", source)

    def test_desktop_navigation_exposes_current_page_semantics(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/components/layout/app-sidebar.tsx"
        )

        self.assertTrue(source.startswith('"use client";'))
        self.assertIn("usePathname", source)
        self.assertIn("isNavigationItemActive", source)
        self.assertIn('aria-current={active ? "page" : undefined}', source)
        self.assertIn('aria-label="주요 메뉴"', source)

    def test_camera_alias_is_used_for_desktop_and_mobile_active_state(self) -> None:
        desktop = read_text(
            "01_frontend/visionflow-web/src/components/layout/app-sidebar.tsx"
        )
        mobile = read_text(
            "01_frontend/visionflow-web/src/components/layout/mobile-navigation.tsx"
        )
        inventory = read_text(
            "01_frontend/visionflow-web/src/components/layout/navigation-items.ts"
        )

        self.assertIn('activeAliases: ["/mobile-camera"]', inventory)
        self.assertIn("item.activeAliases", desktop)
        self.assertIn("item.activeAliases", mobile)

    def test_mobile_navigation_has_dialog_escape_and_focus_contract(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/components/layout/mobile-navigation.tsx"
        )

        for contract in (
            'aria-expanded={open}',
            'aria-controls={panelId}',
            'role="dialog"',
            'aria-modal="true"',
            'event.key === "Escape"',
            'event.key === "Tab"',
            "openerRef.current?.focus()",
            "closeButtonRef.current?.focus()",
            'aria-current={active ? "page" : undefined}',
            'className="lg:hidden"',
            'import { createPortal } from "react-dom";',
            "createPortal(",
            "document.body",
            "vf-mobile-navigation-overlay",
            "z-[1000]",
        ):
            self.assertIn(contract, source)

    def test_header_mounts_mobile_navigation(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/components/layout/app-header.tsx"
        )

        self.assertIn(
            'import { MobileNavigation } from "@/components/layout/mobile-navigation";',
            source,
        )
        self.assertIn(
            "<MobileNavigation operatorSecurity={operatorSecurity} />",
            source,
        )

    def test_drones_unauthenticated_session_redirects_to_login(self) -> None:
        source = read_text(
            "01_frontend/visionflow-web/src/app/drones/page.tsx"
        )

        for contract in (
            'response.status === 401',
            'getOperatorAuthMode() === "session"',
            "buildDronesReturnTo(query)",
            'redirect(`/operator-login?returnTo=${encodeURIComponent(returnTo)}`)',
            "const drones = extractDrones",
        ):
            self.assertIn(contract, source)

        self.assertNotIn(
            "const drones = response.status === 401",
            source,
        )

    def test_ci_runs_when_layout_navigation_changes(self) -> None:
        workflow = read_text(".github/workflows/api-audit.yml")

        self.assertGreaterEqual(
            workflow.count(
                '"01_frontend/visionflow-web/src/components/layout/**"'
            ),
            2,
        )
        self.assertIn(
            '-p "test_visionflow_system_traceability_*.py"',
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
