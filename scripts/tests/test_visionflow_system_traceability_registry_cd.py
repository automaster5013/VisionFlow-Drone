from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
API_WORKFLOW = ROOT / ".github" / "workflows" / "api-audit.yml"
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "docker-publish.yml"
AI_DOCKERIGNORE = ROOT / "03_ai-server" / "visionflow-ai" / ".dockerignore"
MODEL_COMPOSE = ROOT / "compose.model.yaml"


class SystemTraceabilityRegistryCdTest(unittest.TestCase):
    def test_release_ci_runs_full_component_validation(self) -> None:
        source = API_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("pull_request:\n    paths:", source)
        self.assertIn(
            "push:\n    branches:\n      - main\n    paths:",
            source,
        )
        self.assertGreaterEqual(source.count('      - "**"'), 2)

        for path in (
            '"01_frontend/visionflow-web/src/app/events/**"',
            '"02_backend/visionflow-api/src/main/java/**"',
            '"03_ai-server/visionflow-ai/app/**"',
            '"scripts/tests/test_visionflow_system_traceability_*.py"',
        ):
            self.assertGreaterEqual(source.count(path), 2)

        self.assertEqual(source.count("actions/checkout@v6"), 1)
        self.assertEqual(source.count("actions/setup-python@v6"), 1)
        self.assertIn("actions/setup-java@v5", source)
        self.assertIn("actions/setup-node@v6", source)
        self.assertIn("./gradlew test --no-daemon", source)
        self.assertIn("npm run lint", source)
        self.assertIn("npm run build", source)
        self.assertIn("python -m pytest -q", source)

    def test_registry_publish_is_gated_by_successful_main_ci(self) -> None:
        source = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("workflow_run:", source)
        self.assertIn(
            "API contract, security, and system traceability audit",
            source,
        )
        self.assertIn(
            "github.event.workflow_run.conclusion == 'success'",
            source,
        )
        self.assertIn(
            "github.event.workflow_run.event == 'push'",
            source,
        )
        self.assertIn(
            "github.event.workflow_run.head_branch == 'main'",
            source,
        )
        self.assertIn("github.event.workflow_run.head_sha", source)
        self.assertIn("workflow_dispatch:", source)
        self.assertIn(
            "Require successful API audit for exact commit",
            source,
        )

    def test_ai_registry_image_uses_cuda_runtime_but_not_model_weights(
        self,
    ) -> None:
        publish = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
        dockerignore = AI_DOCKERIGNORE.read_text(encoding="utf-8")
        model_compose = MODEL_COMPOSE.read_text(encoding="utf-8")

        self.assertIn("TORCH_VERSION=2.12.1", publish)
        self.assertIn("TORCHVISION_VERSION=0.27.1", publish)
        self.assertIn(
            "TORCH_INDEX_URL=https://download.pytorch.org/whl/cu130",
            publish,
        )
        self.assertIn("models/*.pt", dockerignore)
        self.assertIn("target: /app/models", model_compose)
        self.assertIn("read_only: true", model_compose)

    def test_registry_images_are_immutable_sha_tags(self) -> None:
        source = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn(
            'TAG="${{ matrix.component }}-sha-${{ '
            'needs.prepare.outputs.short_sha }}"',
            source,
        )
        self.assertIn("org.opencontainers.image.revision", source)
        self.assertNotIn(":latest", source)


if __name__ == "__main__":
    unittest.main()
