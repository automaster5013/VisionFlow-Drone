from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AWS = ROOT / "infrastructure" / "aws"

def read(name: str) -> str:
    path = AWS / name
    assert path.is_file(), f"missing: {path}"
    return path.read_text(encoding="utf-8")

def main() -> None:
    readme = read("README.md")
    env_example = read("cloud.env.example")
    deploy = read("deploy-backend-mysql.sh")
    override = read("edge-phase3-reporter.override.example.yaml")
    assert "visionflow_mysql_data" in deploy
    assert "docker volume rm" not in deploy
    assert "down -v" not in deploy
    assert "mysql:8.4" in deploy
    assert "backend-sha-310b4eb" in env_example
    assert "sha256:20185c747bb6f45211b99e69694267ffbd8196fe8e2af51c12e13d4d979b8915" in env_example
    assert "replace-with-" in env_example
    assert "15.165." not in override
    assert "2ba172bf-" not in override
    assert "VISIONFLOW_AWS_BACKEND_URL" in override
    assert "VISIONFLOW_AWS_SESSION_ID" in override
    assert "AI_PHASE3_REPORT_EVENTS" in override
    assert "does not by itself prove DJI Mini 4 Pro video input" in readme
    print("PHASE3_AWS_RUNTIME_ASSETS=PASS")

if __name__ == "__main__":
    main()
