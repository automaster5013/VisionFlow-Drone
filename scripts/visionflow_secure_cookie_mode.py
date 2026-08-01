from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


SETTING_KEY = "VISIONFLOW_WEB_SECURE_COOKIES"
SETTING_VALUE = "true"
CONFIRM_TOKEN = "ENABLE_SECURE_OPERATOR_COOKIES"
FRONTEND_CONTAINER = "visionflow-frontend"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_env(path: Path) -> tuple[bytes, str, str, bool]:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if b"\r\n" in raw else "\n"
    return raw, text, newline, has_bom


def selected_value(text: str) -> tuple[str | None, list[int]]:
    matches: list[tuple[int, str]] = []
    for index, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == SETTING_KEY:
            matches.append((index, value.strip()))
    if len(matches) > 1:
        raise RuntimeError(f"{SETTING_KEY} 설정이 여러 번 선언되어 있습니다.")
    if not matches:
        return None, []
    return matches[0][1], [matches[0][0]]


def updated_env(text: str, newline: str) -> tuple[str, str | None]:
    old_value, indexes = selected_value(text)
    lines = text.splitlines()
    replacement = f"{SETTING_KEY}={SETTING_VALUE}"
    if indexes:
        lines[indexes[0]] = replacement
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# HTTPS operator session cookie")
        lines.append(replacement)
    trailing_newline = text.endswith(("\n", "\r"))
    result = newline.join(lines)
    if trailing_newline or not text:
        result += newline
    return result, old_value


def atomic_write(path: Path, text: str, has_bom: bool) -> None:
    payload = text.encode("utf-8")
    if has_bom:
        payload = b"\xef\xbb\xbf" + payload
    handle = tempfile.NamedTemporaryFile(
        mode="wb",
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp_path = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def compose_command(root: Path) -> list[str]:
    command = ["docker", "compose", "--env-file", str(root / ".env.docker")]
    for name in ("compose.yaml", "compose.gpu.yaml", "compose.mobile-https.yaml"):
        path = root / name
        if path.is_file():
            command.extend(["-f", str(path)])
    return command


def selected_runtime_value() -> str | None:
    completed = subprocess.run(
        [
            "docker",
            "inspect",
            FRONTEND_CONTAINER,
            "--format",
            "{{range .Config.Env}}{{println .}}{{end}}",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    prefix = f"{SETTING_KEY}="
    for line in completed.stdout.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def wait_frontend_healthy(timeout_seconds: int = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    last = "unknown"
    while time.monotonic() < deadline:
        completed = subprocess.run(
            [
                "docker",
                "inspect",
                FRONTEND_CONTAINER,
                "--format",
                "{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if completed.returncode == 0:
            last = completed.stdout.strip()
            print(f"[WAIT] {FRONTEND_CONTAINER}: {last}")
            if last == "running/healthy":
                return
        time.sleep(3)
    raise RuntimeError(f"Frontend가 제한 시간 내 healthy가 되지 않았습니다: {last}")


def write_operation(
    root: Path,
    before: bytes,
    after: bytes,
    old_value: str | None,
    restarted: bool,
) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / "artifacts" / "api-security-hardening" / f"secure-cookie-{stamp}"
    directory.mkdir(parents=True, exist_ok=False)
    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "APPLIED",
        "setting": SETTING_KEY,
        "previousValue": old_value,
        "newValue": SETTING_VALUE,
        "envFileSha256Before": sha256_bytes(before),
        "envFileSha256After": sha256_bytes(after),
        "frontendRestarted": restarted,
        "safety": {
            "credentialValuesCollected": False,
            "databaseMutation": False,
            "containerMutation": restarted,
        },
    }
    path = directory / "operation.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VisionFlow Secure 운영자 세션 쿠키 설정 도구"
    )
    parser.add_argument("--root", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    parser.add_argument("--restart-frontend", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = (args.root or Path(__file__).resolve().parents[1]).resolve()
    env_path = root / ".env.docker"
    if not env_path.is_file():
        print(f"[FAIL] .env.docker 파일이 없습니다: {env_path}", file=sys.stderr)
        return 2

    before, text, newline, has_bom = read_env(env_path)
    current, _ = selected_value(text)
    print("VisionFlow secure cookie mode")
    print(f"Setting: {SETTING_KEY}")
    print(f"Current: {current if current is not None else 'MISSING'}")
    print(f"Target : {SETTING_VALUE}")
    print("Safety : 다른 환경값과 비밀값은 출력하지 않습니다.")

    if not args.apply:
        print("Status : ALREADY_SECURE" if current == SETTING_VALUE else "Status : READY")
        print(f"Apply  : --apply --confirm {CONFIRM_TOKEN}")
        return 0
    if args.confirm != CONFIRM_TOKEN:
        print(f"[FAIL] 확인 문자열이 필요합니다: {CONFIRM_TOKEN}", file=sys.stderr)
        return 2

    updated, old_value = updated_env(text, newline)
    if current != SETTING_VALUE:
        atomic_write(env_path, updated, has_bom)
    after = env_path.read_bytes()
    restarted = False
    if args.restart_frontend:
        command = compose_command(root) + [
            "up",
            "-d",
            "--force-recreate",
            "--no-deps",
            "frontend-web",
        ]
        subprocess.run(command, cwd=root, check=True, timeout=300)
        wait_frontend_healthy()
        restarted = True
        actual = selected_runtime_value()
        if actual != SETTING_VALUE:
            raise RuntimeError(
                f"Frontend 런타임 {SETTING_KEY} 값이 예상과 다릅니다: {actual}"
            )

    report = write_operation(root, before, after, old_value, restarted)
    print("[PASS] Secure 운영자 세션 쿠키 설정이 적용되었습니다.")
    print(f"Frontend restarted: {str(restarted).lower()}")
    print(f"Operation: {report.parent}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1)
