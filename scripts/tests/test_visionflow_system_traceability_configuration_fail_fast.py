from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "visionflow_config_preflight.py"


def load_preflight_module():
    spec = importlib.util.spec_from_file_location(
        "visionflow_config_preflight_under_test",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("configuration preflight module을 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def valid_env_text() -> str:
    return "\n".join(
        (
            "VISIONFLOW_VIEWER_KEY=" + "a1" * 32,
            "VISIONFLOW_OPERATOR_KEY=" + "b2" * 32,
            "VISIONFLOW_ADMIN_KEY=" + "c3" * 32,
            "VISIONFLOW_AI_INTERNAL_KEY=" + "d4" * 32,
            "",
        )
    )


class SystemTraceabilityConfigurationFailFastTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.preflight = load_preflight_module()

    def run_preflight(self, content: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(content, encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = self.preflight.main(
                    ["--root", directory, "--env-file", str(env_path)]
                )
            return exit_code, output.getvalue()

    def test_valid_configuration_passes_without_echoing_secrets(self) -> None:
        content = valid_env_text()
        exit_code, output = self.run_preflight(content)

        self.assertEqual(0, exit_code)
        self.assertIn("VisionFlow configuration preflight: PASS", output)
        self.assertIn("secret-uniqueness", output)
        for secret in (
            "a1" * 32,
            "b2" * 32,
            "c3" * 32,
            "d4" * 32,
        ):
            self.assertNotIn(secret, output)

    def test_missing_required_secret_is_blocked(self) -> None:
        content = valid_env_text().replace(
            "VISIONFLOW_ADMIN_KEY=" + "c3" * 32 + "\n",
            "",
        )
        exit_code, output = self.run_preflight(content)

        self.assertEqual(1, exit_code)
        self.assertIn("VISIONFLOW_ADMIN_KEY: 누락되었습니다.", output)

    def test_duplicate_variable_is_blocked(self) -> None:
        content = valid_env_text() + (
            "VISIONFLOW_VIEWER_KEY=" + "e5" * 32 + "\n"
        )
        exit_code, output = self.run_preflight(content)

        self.assertEqual(1, exit_code)
        self.assertIn("VISIONFLOW_VIEWER_KEY: 중복 선언되었습니다.", output)

    def test_reused_secret_is_blocked(self) -> None:
        content = valid_env_text().replace(
            "VISIONFLOW_OPERATOR_KEY=" + "b2" * 32,
            "VISIONFLOW_OPERATOR_KEY=" + "a1" * 32,
        )
        exit_code, output = self.run_preflight(content)

        self.assertEqual(1, exit_code)
        self.assertIn("보안 키는 서로 달라야 합니다", output)

    def test_placeholder_secret_is_blocked(self) -> None:
        content = valid_env_text().replace(
            "VISIONFLOW_AI_INTERNAL_KEY=" + "d4" * 32,
            "VISIONFLOW_AI_INTERNAL_KEY=change_me_" + "x" * 40,
        )
        exit_code, output = self.run_preflight(content)

        self.assertEqual(1, exit_code)
        self.assertIn("placeholder", output)

    def test_compose_requires_all_operational_security_secrets(self) -> None:
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

        required_contracts = (
            "VISIONFLOW_VIEWER_KEY: "
            "${VISIONFLOW_VIEWER_KEY:?VISIONFLOW_VIEWER_KEY is required}",
            "VISIONFLOW_OPERATOR_KEY: "
            "${VISIONFLOW_OPERATOR_KEY:?VISIONFLOW_OPERATOR_KEY is required}",
            "VISIONFLOW_ADMIN_KEY: "
            "${VISIONFLOW_ADMIN_KEY:?VISIONFLOW_ADMIN_KEY is required}",
        )
        for contract in required_contracts:
            self.assertIn(contract, compose)

        ai_contract = (
            "VISIONFLOW_AI_INTERNAL_KEY: "
            "${VISIONFLOW_AI_INTERNAL_KEY:?"
            "VISIONFLOW_AI_INTERNAL_KEY is required}"
        )
        self.assertEqual(3, compose.count(ai_contract))

    def test_example_documents_required_security_variables(self) -> None:
        example = (ROOT / ".env.example").read_text(encoding="utf-8")

        for name in self.preflight.REQUIRED_SECRET_NAMES:
            self.assertIn(f"{name}=", example)
        self.assertIn("VISIONFLOW_WEB_AUTH_MODE=session", example)
        self.assertIn("VISIONFLOW_WEB_SECURE_COOKIES=true", example)
        self.assertIn("python scripts/visionflow_config_preflight.py", example)

    def test_ci_tracks_configuration_contract(self) -> None:
        workflow = (
            ROOT / ".github" / "workflows" / "api-audit.yml"
        ).read_text(encoding="utf-8")

        for path in (
            '".env.example"',
            '"compose.yaml"',
            '"scripts/visionflow_config_preflight.py"',
            '"docs/README-security-configuration.md"',
        ):
            self.assertGreaterEqual(workflow.count(path), 2)

        self.assertIn(
            "scripts/visionflow_config_preflight.py \\",
            workflow,
        )
        self.assertIn(
            '-p "test_visionflow_system_traceability_*.py"',
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
