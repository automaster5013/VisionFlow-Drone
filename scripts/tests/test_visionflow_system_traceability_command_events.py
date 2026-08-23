from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
EVENT_CENTER = ROOT / "01_frontend/visionflow-web/src/components/events/event-operations-center.tsx"
EVENT_DRAWER = ROOT / "01_frontend/visionflow-web/src/components/events/event-detail-drawer.tsx"
SNAPSHOT_CONTROL = ROOT / "01_frontend/visionflow-web/src/components/events/manual-snapshot-control.tsx"
GLOBALS_CSS = ROOT / "01_frontend/visionflow-web/src/app/globals.css"


class CommandEventsTraceabilityTest(unittest.TestCase):
    def test_semantic_command_surface_classes_are_present(self) -> None:
        center = EVENT_CENTER.read_text(encoding="utf-8")
        drawer = EVENT_DRAWER.read_text(encoding="utf-8")
        snapshot = SNAPSHOT_CONTROL.read_text(encoding="utf-8")

        for marker in (
            "vf-event-command",
            "vf-event-command__hero",
            "vf-event-command__summary",
            "vf-event-command__filters",
            "vf-event-command__timeline",
            "vf-event-command__event",
            "vf-event-command__event-action",
        ):
            self.assertIn(marker, center)

        for marker in (
            "vf-event-drawer",
            "vf-event-drawer__panel",
            "vf-event-drawer__header",
            "vf-event-drawer__section",
            "vf-event-drawer__evidence",
            "vf-event-drawer__metric",
            "vf-event-drawer__actions",
        ):
            self.assertIn(marker, drawer)

        for marker in (
            "vf-event-snapshot",
            "vf-event-snapshot__form",
            "vf-event-snapshot__input",
            "vf-event-snapshot__confirm",
            "vf-event-snapshot__submit",
        ):
            self.assertIn(marker, snapshot)

    def test_existing_event_runtime_contracts_are_preserved(self) -> None:
        center = EVENT_CENTER.read_text(encoding="utf-8")
        drawer = EVENT_DRAWER.read_text(encoding="utf-8")
        snapshot = SNAPSHOT_CONTROL.read_text(encoding="utf-8")

        for endpoint in (
            'fetchJson("/api/drones"',
            'fetchJson("/api/ai/events?limit=100"',
            'fetchJson("/api/ai/phase3/events?limit=100"',
            'fetchJson("/api/ai/alerts?limit=200"',
            'fetchJson("/api/geofences/events?activeOnly=false&limit=100"',
            'fetchJson("/api/incidents?limit=200"',
        ):
            self.assertIn(endpoint, center)

        self.assertIn('/api/ai/events/${event.snapshotEventId}/snapshot', drawer)
        self.assertIn('method: "PUT"', snapshot)
        self.assertIn('/api/ai/events/${eventId}/snapshot', snapshot)
        self.assertIn("MAX_SNAPSHOT_BYTES = 10 * 1024 * 1024", snapshot)
        self.assertIn('document.body.style.overflow = "hidden"', drawer)
        self.assertIn('keyboardEvent.key === "Escape"', drawer)

    def test_phase_1e_css_uses_shared_command_tokens(self) -> None:
        css = GLOBALS_CSS.read_text(encoding="utf-8")
        self.assertIn("Phase 1E: unified event and Incident command surfaces", css)
        for selector in (
            ".vf-event-command__hero",
            ".vf-event-command__summary",
            ".vf-event-command__error :is(h2, li, p)",
            ".vf-event-command__event",
            ".vf-event-drawer__panel",
            ".vf-event-drawer__metric",
            ".vf-event-snapshot__submit",
        ):
            self.assertIn(selector, css)

        for token in (
            "var(--vf-surface-1)",
            "var(--vf-bg-elevated)",
            "var(--vf-border)",
            "var(--vf-text-primary)",
            "var(--vf-accent)",
            "var(--vf-sidebar-bg)",
        ):
            self.assertIn(token, css)


if __name__ == "__main__":
    unittest.main()
