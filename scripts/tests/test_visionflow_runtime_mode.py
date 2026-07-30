from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from visionflow_runtime_mode import (  # noqa: E402
    AMBIGUOUS,
    MOBILE_READY,
    PORT_CONFLICT,
    PRESENTATION_READY,
    STOPPED,
    ProbeResult,
    classify_state,
    compose_base,
    probe_endpoint,
)


class RuntimeModeClassificationTests(unittest.TestCase):
    def test_detects_presentation_http(self) -> None:
        result = classify_state(
            ProbeResult(True, 200),
            ProbeResult(False, error="SSLError"),
            (100,),
        )
        self.assertEqual(PRESENTATION_READY, result)

    def test_detects_mobile_https(self) -> None:
        result = classify_state(
            ProbeResult(False, error="ConnectionResetError"),
            ProbeResult(True, 200),
            (200,),
        )
        self.assertEqual(MOBILE_READY, result)

    def test_detects_stopped_frontend(self) -> None:
        result = classify_state(
            ProbeResult(False, error="ConnectionRefusedError"),
            ProbeResult(False, error="ConnectionRefusedError"),
            (),
        )
        self.assertEqual(STOPPED, result)

    def test_detects_unknown_port_owner(self) -> None:
        result = classify_state(
            ProbeResult(False, error="TimeoutError"),
            ProbeResult(False, error="TimeoutError"),
            (333,),
        )
        self.assertEqual(PORT_CONFLICT, result)

    def test_detects_ambiguous_protocol_state(self) -> None:
        result = classify_state(
            ProbeResult(True, 200),
            ProbeResult(True, 200),
            (444,),
        )
        self.assertEqual(AMBIGUOUS, result)


class ComposeCommandTests(unittest.TestCase):
    def test_compose_base_requires_expected_files(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
            (root / ".env.docker").write_text("", encoding="utf-8")
            command = compose_base(root)

        self.assertEqual("docker", command[0])
        self.assertIn("--env-file", command)
        self.assertIn("-f", command)

    def test_compose_base_rejects_missing_environment(self) -> None:
        from tempfile import TemporaryDirectory
        from visionflow_runtime_mode import RuntimeModeError

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
            with self.assertRaises(RuntimeModeError):
                compose_base(root)


class ProbePolicyTests(unittest.TestCase):
    def test_default_probe_timeout_allows_next_initial_compilation(self) -> None:
        import inspect

        timeout = inspect.signature(probe_endpoint).parameters["timeout"].default
        self.assertGreaterEqual(timeout, 8.0)


if __name__ == "__main__":
    unittest.main()
