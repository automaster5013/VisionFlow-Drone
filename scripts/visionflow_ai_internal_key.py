from __future__ import annotations

import argparse
import os
import secrets
import string
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SETTING_KEY = "VISIONFLOW_AI_INTERNAL_KEY"
MINIMUM_LENGTH = 32
GENERATED_LENGTH = 48
ENSURE_CONFIRM_TOKEN = "ENSURE_VISIONFLOW_AI_INTERNAL_KEY"
ROTATE_CONFIRM_TOKEN = "ROTATE_VISIONFLOW_AI_INTERNAL_KEY"
PLACEHOLDER_MARKERS = ("replace-with", "change-me", "example", "placeholder")
ALPHABET = string.ascii_letters + string.digits + "-_"


def read_env(path: Path) -> tuple[bytes, str, str, bool]:
    raw = path.read_bytes()
    return (
        raw,
        raw.decode("utf-8-sig"),
        "\r\n" if b"\r\n" in raw else "\n",
        raw.startswith(b"\xef\xbb\xbf"),
    )


def selected_value(text: str) -> tuple[str | None, int | None]:
    matches: list[tuple[int, str]] = []
    for index, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == SETTING_KEY:
            value = value.strip()
            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in {'"', "'"}
            ):
                value = value[1:-1]
            matches.append((index, value))
    if len(matches) > 1:
        raise RuntimeError(f"{SETTING_KEY} 설정이 여러 번 선언되어 있습니다.")
    if not matches:
        return None, None
    return matches[0][1], matches[0][0]


def is_placeholder(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def is_valid(value: str | None) -> bool:
    return bool(
        value
        and len(value) >= MINIMUM_LENGTH
        and not is_placeholder(value)
    )


def generate_key() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(GENERATED_LENGTH))


def updated_env(text: str, newline: str, value: str) -> str:
    _, index = selected_value(text)
    lines = text.splitlines()
    replacement = f"{SETTING_KEY}={value}"
    if index is not None:
        lines[index] = replacement
    else:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# AI service-to-service authentication (do not share)")
        lines.append(replacement)
    trailing_newline = text.endswith(("\r", "\n"))
    result = newline.join(lines)
    if trailing_newline or not text:
        result += newline
    return result


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
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def backup_env(root: Path, env_path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root / "artifacts" / "config-backups" / f"ai-internal-key-{stamp}"
    directory.mkdir(parents=True, exist_ok=False)
    backup = directory / env_path.name
    backup.write_bytes(env_path.read_bytes())
    return backup


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VisionFlow AI 내부 서비스 키 준비 도구"
    )
    parser.add_argument("--root", type=Path)
    parser.add_argument("command", choices=("plan", "ensure", "rotate"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = (args.root or Path(__file__).resolve().parents[1]).resolve()
    env_path = root / ".env.docker"
    if not env_path.is_file():
        print(f"[FAIL] .env.docker 파일이 없습니다: {env_path}", file=sys.stderr)
        return 2

    _, text, newline, has_bom = read_env(env_path)
    current, _ = selected_value(text)
    valid = is_valid(current)
    print("VisionFlow AI internal service key")
    print(f"Environment: {env_path}")
    print(f"Present: {str(bool(current)).lower()}")
    print(f"Length : {len(current) if current else 0}")
    print(f"Valid  : {str(valid).lower()}")
    print("Safety : 키 값은 출력하지 않습니다.")

    if args.command == "plan":
        print("Status : READY" if not valid else "Status : ALREADY_READY")
        print(
            "Apply  : ensure --apply --confirm "
            f"{ENSURE_CONFIRM_TOKEN}"
        )
        return 0

    confirm_token = (
        ENSURE_CONFIRM_TOKEN if args.command == "ensure" else ROTATE_CONFIRM_TOKEN
    )
    if not args.apply:
        status = "ALREADY_READY" if args.command == "ensure" and valid else "READY"
        print(f"Status : {status}")
        print(f"Apply  : {args.command} --apply --confirm {confirm_token}")
        return 0
    if args.confirm != confirm_token:
        print(f"[FAIL] 확인 문자열이 필요합니다: {confirm_token}", file=sys.stderr)
        return 2
    if args.command == "ensure" and valid:
        print("Status : ALREADY_READY")
        print("Changed: false")
        return 0

    backup = backup_env(root, env_path)
    generated = generate_key()
    atomic_write(env_path, updated_env(text, newline, generated), has_bom)
    print("Status : GENERATED" if args.command == "ensure" else "Status : ROTATED")
    print("Changed: true")
    print(f"Length : {GENERATED_LENGTH}")
    print(f"Backup : {backup}")
    print("Recreate ai-server and frontend-web before validation.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1)
