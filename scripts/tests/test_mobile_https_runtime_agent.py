from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
AGENT_PATH = (
    ROOT
    / "scripts"
    / "mobile-https-runtime"
    / "mobile_https_runtime_agent.py"
)
SPEC = importlib.util.spec_from_file_location(
    "mobile_https_runtime_agent",
    AGENT_PATH,
)
assert SPEC is not None
assert SPEC.loader is not None
agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(agent)


class MobileHttpsRuntimeAgentTests(unittest.TestCase):
    def test_lan_ipv4_accepts_rfc1918_only(self) -> None:
        self.assertTrue(agent.is_lan_ipv4("192.168.45.10"))
        self.assertTrue(agent.is_lan_ipv4("10.20.30.40"))
        self.assertTrue(agent.is_lan_ipv4("172.16.1.9"))
        self.assertFalse(agent.is_lan_ipv4("127.0.0.1"))
        self.assertFalse(agent.is_lan_ipv4("169.254.1.1"))
        self.assertFalse(agent.is_lan_ipv4("8.8.8.8"))

    def test_explicit_host_ip_becomes_runtime_origin(self) -> None:
        with (
            patch.object(
                agent,
                "local_ipv4_candidates",
                return_value=(["192.168.45.20"], "192.168.45.20"),
            ),
            patch.object(Path, "is_file", return_value=False),
        ):
            profile = agent.build_profile(
                root=Path("C:/VisionFlow-Drone"),
                port=3443,
                explicit_host_ip="192.168.45.77",
            )

        self.assertEqual(profile["hostIp"], "192.168.45.77")
        self.assertEqual(
            profile["origin"],
            "https://192.168.45.77:3443",
        )
        self.assertEqual(profile["detectionSource"], "explicit")
        self.assertFalse(profile["ready"])

    def test_default_route_is_preferred(self) -> None:
        with (
            patch.object(
                agent,
                "local_ipv4_candidates",
                return_value=(
                    ["192.168.45.20", "192.168.46.7"],
                    "192.168.45.20",
                ),
            ),
            patch.object(Path, "is_file", return_value=False),
        ):
            profile = agent.build_profile(
                root=Path("C:/VisionFlow-Drone"),
                port=3443,
            )

        self.assertEqual(profile["hostIp"], "192.168.45.20")
        self.assertEqual(
            profile["detectionSource"],
            "udp-default-route",
        )

    def test_invalid_explicit_host_ip_is_rejected(self) -> None:
        with self.assertRaises(agent.RuntimeAgentError):
            agent.build_profile(
                root=Path("C:/VisionFlow-Drone"),
                port=3443,
                explicit_host_ip="8.8.8.8",
            )


if __name__ == "__main__":
    unittest.main()
