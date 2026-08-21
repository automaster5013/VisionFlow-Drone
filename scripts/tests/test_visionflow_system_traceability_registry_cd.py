from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
API_WORKFLOW = ROOT / ".github" / "workflows" / "api-audit.yml"
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "docker-publish.yml"
PLANNER = ROOT / "scripts" / "visionflow_container_release_plan.py"
AI_DOCKERIGNORE = ROOT / "03_ai-server" / "visionflow-ai" / ".dockerignore"
MODEL_COMPOSE = ROOT / "compose.model.yaml"


class SystemTraceabilityRegistryCdTest(unittest.TestCase):
    def test_release_ci_runs_full_component_validation(self) -> None:
        source = API_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("pull_request:\n    paths:", source)
        self.assertIn(
            "push:\n    branches:\n      - main\n      - \"feature/**\"\n    paths:",
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
        self.assertIn(
            "Start isolated MySQL 8.4 for backend tests",
            source,
        )
        self.assertIn("mysql:8.4", source)
        self.assertIn(
            "--collation-server=utf8mb4_unicode_ci",
            source,
        )
        self.assertIn(
            "SPRING_DATASOURCE_URL: "
            "jdbc:mysql://127.0.0.1:3306/visionflow",
            source,
        )
        self.assertIn("Stop isolated MySQL", source)
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
        self.assertIn(
            "types:\n      - completed\n    branches:\n      - main",
            source,
        )
        self.assertIn("github.event.workflow_run.head_sha", source)
        self.assertIn("workflow_dispatch:", source)
        self.assertIn(
            "Require successful API audit for exact commit",
            source,
        )


    def test_registry_publish_skips_non_image_changes_but_keeps_atomic_release(
        self,
    ) -> None:
        source = PUBLISH_WORKFLOW.read_text(encoding="utf-8")
        planner = PLANNER.read_text(encoding="utf-8")

        # Embedded Python must remain inside the YAML literal block.
        self.assertNotIn("\nimport json\n", source)
        self.assertNotIn("\nimport os\n", source)
        self.assertNotIn("\nimport sys\n", source)

        self.assertIn("Plan container release", source)
        self.assertIn(
            "scripts/visionflow_container_release_plan.py",
            source,
        )
        self.assertIn(
            "api-audit.yml/runs?branch=main&event=push",
            source,
        )
        self.assertIn(
            "if: needs.prepare.outputs.release_required == 'true'",
            source,
        )
        self.assertIn(
            "if: steps.release-plan.outputs.release_required == 'true'",
            source,
        )

        for prefix in (
            "01_frontend/visionflow-web/",
            "02_backend/visionflow-api/",
            "03_ai-server/visionflow-ai/",
        ):
            self.assertIn(prefix, planner)

        self.assertIn(
            ".github/workflows/docker-publish.yml",
            planner,
        )
        self.assertIn(
            "no-docker-build-context-change",
            planner,
        )

        for component in ("frontend", "backend", "ai"):
            self.assertEqual(
                source.count(f"- component: {component}"),
                1,
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

    def test_ai_registry_image_runtime_contract(self) -> None:
        source = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("Verify AI image runtime contract", source)
        self.assertIn("docker pull \"${IMAGE_REF}\"", source)
        self.assertIn("org.opencontainers.image.revision", source)
        self.assertIn(
            "torch.__version__ == '2.12.1+cu130'",
            source,
        )
        self.assertIn("torch.version.cuda == '13.0'", source)
        self.assertIn("shutil.which('ffmpeg')", source)
        self.assertIn("create_dji_live_source", source)
        self.assertIn("DjiAndroidBridgeSource", source)
        self.assertIn(
            "pathlib.Path('/app/models').glob('*.pt')",
            source,
        )
        self.assertIn("AI_IMAGE_RUNTIME_CONTRACT=PASS", source)

    def test_registry_publish_verifies_complete_sha_release_set(self) -> None:
        source = PUBLISH_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("verify-release-set:", source)
        self.assertIn("name: Verify immutable release set", source)
        self.assertIn(
            "needs:\n      - prepare\n      - publish",
            source,
        )
        self.assertIn(
            "Verify all component SHA tags exist",
            source,
        )
        self.assertIn(
            "for component in frontend backend ai; do",
            source,
        )
        self.assertIn(
            'REF="${IMAGE}:${component}-sha-${SHORT_SHA}"',
            source,
        )
        self.assertIn("RELEASE_SET=PASS", source)


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
