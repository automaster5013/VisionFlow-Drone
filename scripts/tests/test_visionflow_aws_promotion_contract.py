from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AWS_DIR = ROOT / "infrastructure" / "aws"
PROMOTION_SCRIPT = AWS_DIR / "promote-backend.sh"
ENV_EXAMPLE = AWS_DIR / "cloud.env.example"
README = AWS_DIR / "README.md"

EXPECTED_IMAGE = "automaster5013/visionflow-drone:backend-sha-52e847e"
EXPECTED_DIGEST = "sha256:94d53419ae1a93809c7692350db792b208ee488813f62fd64b17dc4b586a06b3"


class VisionFlowAwsPromotionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = PROMOTION_SCRIPT.read_text(encoding="utf-8")
        cls.env = ENV_EXAMPLE.read_text(encoding="utf-8")
        cls.readme = README.read_text(encoding="utf-8")

    def _function_body(self, name: str, next_name: str) -> str:
        start = self.script.index(f"{name}() {{")
        end = self.script.index(f"\n{next_name}() {{", start)
        return self.script[start:end]

    def test_release_metadata_is_pinned_to_day4_immutable_release(self) -> None:
        self.assertIn(f"VISIONFLOW_BACKEND_IMAGE={EXPECTED_IMAGE}", self.env)
        self.assertIn(f"VISIONFLOW_BACKEND_EXPECTED_DIGEST={EXPECTED_DIGEST}", self.env)
        self.assertIn(EXPECTED_IMAGE, self.readme)
        self.assertIn(EXPECTED_DIGEST, self.readme)

    def test_candidate_requires_immutable_tag_and_registry_digest(self) -> None:
        self.assertIn(":backend-sha-[0-9a-f]{7,40}", self.script)
        self.assertIn("^sha256:[0-9a-f]{64}$", self.script)
        self.assertIn("docker pull \"$CANDIDATE_IMAGE\"", self.script)
        self.assertIn("grep -F \"@${EXPECTED_DIGEST}\"", self.script)
        self.assertIn("Candidate image digest does not match expected digest", self.script)

    def test_smoke_is_loopback_only_and_must_match_candidate_image(self) -> None:
        self.assertIn('-p "127.0.0.1:${SMOKE_PORT}:${CONTAINER_PORT}"', self.script)
        self.assertIn('[[ "$image_id" == "$CANDIDATE_IMAGE_ID" ]]', self.script)
        self.assertIn('"HostIp":"127.0.0.1"', self.script)
        self.assertIn("VISIONFLOW_PHASE3_EVENT_INGEST", self.script)
        self.assertIn("VISIONFLOW_PHASE3_DEPTH_ENRICH", self.script)

    def test_runtime_drift_fails_closed_before_recreation(self) -> None:
        guard = self._function_body("assert_supported_current_runtime", "assert_supported_smoke_runtime")
        self.assertIn('[[ "$network" == "$NETWORK_NAME" ]]', guard)
        self.assertIn('[[ "$restart_policy" == "unless-stopped" ]]', guard)
        self.assertIn('[[ "$mount_count" == "0" ]]', guard)
        self.assertIn("does not publish expected host port", guard)
        self.assertIn('memory="$(docker inspect --format \'{{.HostConfig.Memory}}\' "$CURRENT_CONTAINER")"', self.script)
        self.assertIn('resource_args+=(--memory "${memory}b")', self.script)
        self.assertIn('resource_args+=(--memory-swap "${memory_swap}b")', self.script)

    def test_preflight_happens_before_destructive_promotion_steps(self) -> None:
        promote = self._function_body("promote", "rollback")
        positions = [
            promote.index("preflight"),
            promote.index('PROMOTION_STEP=remove_smoke'),
            promote.index('PROMOTION_STEP=stop_current'),
            promote.index('PROMOTION_STEP=preserve_current_as_rollback'),
            promote.index('PROMOTION_STEP=start_candidate_on_8080'),
        ]
        self.assertEqual(positions, sorted(positions))

    def test_previous_backend_is_preserved_with_restart_disabled(self) -> None:
        promote = self._function_body("promote", "rollback")
        self.assertIn('docker rename "$CURRENT_CONTAINER" "$backup_container"', promote)
        self.assertIn('docker update --restart=no "$backup_container"', promote)
        self.assertIn('BACKUP_STATE=stopped', promote)

    def test_automatic_rollback_restores_previous_restart_policy_and_health(self) -> None:
        promote = self._function_body("promote", "rollback")
        rollback_start = promote.index("rollback_automatically() {")
        rollback_end = promote.index('log "PROMOTION_STEP=start_candidate_on_8080"', rollback_start)
        rollback = promote[rollback_start:rollback_end]
        self.assertIn('docker rename "$backup_container" "$CURRENT_CONTAINER"', rollback)
        self.assertIn('docker update --restart="$restart_policy" "$CURRENT_CONTAINER"', rollback)
        self.assertIn('docker start "$CURRENT_CONTAINER"', rollback)
        self.assertIn('wait_for_health "$CURRENT_HEALTH_URL"', rollback)
        self.assertIn('AWS_BACKEND_PROMOTION=ROLLED_BACK', rollback)

    def test_manual_rollback_preserves_forward_recovery_and_health_gate(self) -> None:
        rollback = self._function_body("rollback", "usage")
        self.assertIn("rollback <backup-container-name>", rollback)
        self.assertIn('[[ "$backup_container" == "${CURRENT_CONTAINER}-rollback-"* ]]', rollback)
        self.assertIn('container_exists "$backup_container"', rollback)
        self.assertIn('container_exists "$CURRENT_CONTAINER"', rollback)
        self.assertIn('rescue_container="${CURRENT_CONTAINER}-rollback-rescue-${timestamp}"', rollback)
        self.assertIn('docker stop --time 30 "$CURRENT_CONTAINER"', rollback)
        self.assertIn('docker rename "$CURRENT_CONTAINER" "$rescue_container"', rollback)
        self.assertIn('docker update --restart=no "$rescue_container"', rollback)
        self.assertIn('docker rename "$backup_container" "$CURRENT_CONTAINER"', rollback)
        self.assertIn('docker update --restart="$restart_policy" "$CURRENT_CONTAINER"', rollback)
        self.assertIn('wait_for_health "$CURRENT_HEALTH_URL"', rollback)
        self.assertIn('AWS_BACKEND_MANUAL_ROLLBACK=RECOVERED', rollback)
        self.assertIn('AWS_BACKEND_MANUAL_ROLLBACK=PASS', rollback)
        self.assertIn('FORWARD_RECOVERY_CONTAINER=$rescue_container', rollback)
        self.assertNotIn('docker rm -f "$CURRENT_CONTAINER"', rollback)

    def test_runtime_secrets_are_not_persisted_in_rollback_metadata(self) -> None:
        self.assertIn("mktemp /tmp/visionflow-backend-runtime.", self.script)
        self.assertIn('chmod 600 "$PROMOTION_ENV_FILE"', self.script)
        self.assertIn('rm -f "$PROMOTION_ENV_FILE"', self.script)
        self.assertIn("write_container_runtime_metadata()", self.script)
        self.assertIn("current-container.runtime.txt", self.script)
        self.assertIn("smoke-container.runtime.txt", self.script)
        self.assertIn("promoted-container.runtime.txt", self.script)
        self.assertIn("candidate-image.release.txt", self.script)
        self.assertNotIn('current-container.inspect.json', self.script)
        self.assertNotIn('smoke-container.inspect.json', self.script)
        self.assertNotIn('promoted-container.inspect.json', self.script)
        deployment_block = re.search(
            r'cat > "\$\{rollback_dir\}/deployment\.env" <<META\n(?P<body>.*?)\nMETA',
            self.script,
            re.DOTALL,
        )
        self.assertIsNotNone(deployment_block)
        assert deployment_block is not None
        self.assertNotIn("PASSWORD", deployment_block.group("body"))
        self.assertNotIn("VISIONFLOW_OPERATOR_KEY", deployment_block.group("body"))

    def test_promotion_script_does_not_manage_mysql_or_docker_volumes(self) -> None:
        forbidden = (
            "docker volume rm",
            "docker volume prune",
            "docker compose down -v",
            "visionflow_mysql_data",
            "visionflow-mysql-cloud",
            "3306:3306",
        )
        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, self.script)


if __name__ == "__main__":
    unittest.main()
