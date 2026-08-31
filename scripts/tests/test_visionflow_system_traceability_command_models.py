from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "01_frontend" / "visionflow-web" / "src"


def source(relative: str) -> str:
    return (WEB / relative).read_text(encoding="utf-8")


class AiModelCommandSurfaceTraceabilityTest(unittest.TestCase):
    def test_model_semantic_command_surfaces_are_present(self) -> None:
        center = source("components/models/ai-model-operations-center.tsx")
        for marker in (
            "data-ai-model-command-center",
            "vf-model-command__hero",
            "vf-model-command__summary",
            "vf-model-command__metric",
            "vf-model-command__health",
            "vf-model-command__source-chip",
            "vf-model-command__panel",
            "vf-model-command__detail",
            "vf-model-command__runtime-note",
            "vf-model-command__link",
        ):
            self.assertIn(marker, center)

    def test_existing_read_only_model_runtime_contract_is_preserved(self) -> None:
        page = source("app/models/page.tsx")
        center = source("components/models/ai-model-operations-center.tsx")

        self.assertIn('requireOperatorAuthentication("/models")', page)
        self.assertIn('export const dynamic = "force-dynamic"', page)
        for endpoint in (
            "/api/ai/models/status",
            "/api/ai/metrics/status",
            "/api/ai/ingest/status",
            "/api/ai/stream/status",
            "/api/ai/alerts?limit=100",
        ):
            self.assertIn(endpoint, center)

        for contract in (
            "Promise.allSettled",
            "AbortController",
            "AUTO_REFRESH_INTERVAL_MS = 30_000",
            "readOperatorConsolePreferences",
            'document.visibilityState === "visible"',
            "마지막 정상 데이터를 유지합니다.",
        ):
            self.assertIn(contract, center)

    def test_phase_1h_theme_and_responsive_contract_uses_shared_tokens(self) -> None:
        css = source("app/globals.css")
        for selector in (
            "/* Phase 1H: AI model command surfaces. */",
            ".vf-model-command__hero",
            ".vf-model-command__summary",
            ".vf-model-command__metric",
            ".vf-model-command__health--critical",
            ".vf-model-command__source-chip--degraded",
            ".vf-model-command__panel",
            ".vf-model-command__link--primary",
            "@media (max-width: 767px)",
        ):
            self.assertIn(selector, css)

        for token in (
            "var(--vf-surface-1)",
            "var(--vf-surface-2)",
            "var(--vf-surface-3)",
            "var(--vf-border)",
            "var(--vf-text-primary)",
            "var(--vf-text-secondary)",
            "var(--vf-accent)",
        ):
            self.assertIn(token, css)


if __name__ == "__main__":
    unittest.main()
