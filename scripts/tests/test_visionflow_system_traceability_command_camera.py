from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "01_frontend" / "visionflow-web" / "src"


def read_frontend(relative_path: str) -> str:
    return (FRONTEND / relative_path).read_text(encoding="utf-8")


class CommandCameraTraceabilityTests(unittest.TestCase):
    def test_camera_input_uses_semantic_command_surfaces(self) -> None:
        streamer = read_frontend(
            "components/mobile/mobile-camera-streamer.tsx"
        )
        preview = read_frontend(
            "components/mobile/mobile-ai-inference-preview.tsx"
        )
        page = read_frontend("app/ai-preview/page.tsx")

        for name in (
            "vf-camera-command",
            "vf-camera-command__hero",
            "vf-camera-command__config",
            "vf-camera-command__preview-grid",
            "vf-camera-command__preview",
            "vf-camera-command__status",
            "vf-camera-command__metric",
            "vf-camera-command__actions",
        ):
            self.assertIn(name, streamer)

        for name in (
            "vf-ai-preview",
            "vf-ai-preview__header",
            "vf-ai-preview__state",
            "vf-ai-preview__viewport",
            "vf-ai-preview__metrics",
            "vf-ai-preview__metric",
        ):
            self.assertIn(name, preview)

        self.assertIn("vf-camera-preview-page", page)

    def test_camera_command_aligns_with_shared_shell_content_grid(self) -> None:
        streamer = read_frontend(
            "components/mobile/mobile-camera-streamer.tsx"
        )
        layout = read_frontend("app/layout.tsx")

        self.assertIn(
            '<main className="vf-command-main flex-1 p-4 sm:p-6 xl:p-7">',
            layout,
        )
        self.assertIn("data-mobile-camera-command", streamer)
        self.assertIn(
            'className="vf-camera-command min-h-full text-slate-900"',
            streamer,
        )
        self.assertIn(
            'className="mx-auto max-w-[1500px] space-y-5"',
            streamer,
        )
        self.assertNotIn("min-h-screen px-4 py-6", streamer)
        self.assertNotIn("max-w-7xl", streamer)
        self.assertNotIn("<main", streamer)

    def test_camera_command_preserves_capture_and_ai_api_contracts(self) -> None:
        streamer = read_frontend(
            "components/mobile/mobile-camera-streamer.tsx"
        )
        preview = read_frontend(
            "components/mobile/mobile-ai-inference-preview.tsx"
        )

        for contract in (
            'fetch("/api/drones"',
            "navigator.mediaDevices.getUserMedia",
            "canvasToJpeg(canvas, jpegQuality)",
            "`/api/ai/ingest/frame?${query.toString()}`",
            'fetch("/api/ai/ingest/status"',
            '"Content-Type": "image/jpeg"',
        ):
            self.assertIn(contract, streamer)

        for contract in (
            'fetch("/api/ai/stream/status"',
            "getAiStreamUrl()",
            'window.open(\n      "/ai-preview"',
        ):
            self.assertIn(contract, preview)

    def test_camera_surfaces_use_shared_theme_tokens_without_runtime_mutation(
        self,
    ) -> None:
        css = read_frontend("app/globals.css")

        for token in (
            "--vf-surface-1",
            "--vf-surface-2",
            "--vf-border",
            "--vf-accent",
            "--vf-success",
            "--vf-warning",
            "--vf-danger",
            "--vf-shadow",
        ):
            self.assertIn(token, css)

        for selector in (
            ".vf-camera-command__hero",
            ".vf-camera-command__config",
            ".vf-camera-command__preview",
            ".vf-camera-command__status",
            ".vf-ai-preview__metrics",
            ".vf-camera-preview-page",
        ):
            self.assertIn(selector, css)

        phase_paths = {
            "01_frontend/visionflow-web/src/app/ai-preview/page.tsx",
            "01_frontend/visionflow-web/src/app/globals.css",
            "01_frontend/visionflow-web/src/components/mobile/mobile-ai-inference-preview.tsx",
            "01_frontend/visionflow-web/src/components/mobile/mobile-camera-streamer.tsx",
            "scripts/tests/test_visionflow_system_traceability_command_camera.py",
        }
        self.assertFalse(
            any(
                path.startswith(("02_backend/", "03_ai-server/"))
                or "compose" in path
                for path in phase_paths
            )
        )


if __name__ == "__main__":
    unittest.main()
