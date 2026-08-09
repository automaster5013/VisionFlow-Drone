from __future__ import annotations

import argparse
import re
from pathlib import Path


MIN_SECRET_LENGTH = 32
REQUIRED_SECRET_NAMES = (
    "VISIONFLOW_VIEWER_KEY",
    "VISIONFLOW_OPERATOR_KEY",
    "VISIONFLOW_ADMIN_KEY",
    "VISIONFLOW_AI_INTERNAL_KEY",
)
PLACEHOLDER_MARKERS = (
    "change_me",
    "changeme",
    "replace_me",
    "replace-with",
    "replace_with",
    "your_secret",
    "your-key",
    "example-secret",
    "example_key",
    "<secret",
    "<key",
    "todo",
)
ENV_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_env_file(path: Path) -> tuple[dict[str, str], dict[str, list[int]], list[str]]:
    values: dict[str, str] = {}
    occurrences: dict[str, list[int]] = {}
    syntax_errors: list[str] = []

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(),
        start=1,
    ):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        if "=" not in stripped:
            syntax_errors.append(f"line {line_number}: '=' 구분자가 없습니다.")
            continue

        name, raw_value = stripped.split("=", 1)
        name = name.strip()
        value = raw_value.strip()

        if not ENV_NAME_PATTERN.fullmatch(name):
            syntax_errors.append(
                f"line {line_number}: 환경변수 이름이 올바르지 않습니다: {name!r}"
            )
            continue

        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]

        occurrences.setdefault(name, []).append(line_number)
        values[name] = value

    return values, occurrences, syntax_errors


def validate_security_configuration(
    values: dict[str, str],
    occurrences: dict[str, list[int]],
    syntax_errors: list[str],
) -> list[str]:
    failures = list(syntax_errors)
    validated: dict[str, str] = {}

    for name in REQUIRED_SECRET_NAMES:
        lines = occurrences.get(name, [])
        if not lines:
            failures.append(f"{name}: 누락되었습니다.")
            continue
        if len(lines) != 1:
            failures.append(
                f"{name}: 중복 선언되었습니다. lines={','.join(map(str, lines))}"
            )
            continue

        value = values.get(name, "")
        if not value:
            failures.append(f"{name}: 값이 비어 있습니다.")
            continue
        if any(character.isspace() for character in value):
            failures.append(f"{name}: 공백 문자를 포함할 수 없습니다.")
            continue
        if len(value) < MIN_SECRET_LENGTH:
            failures.append(
                f"{name}: 최소 {MIN_SECRET_LENGTH}자 이상이어야 합니다. "
                f"actual={len(value)}"
            )
            continue

        normalized = value.casefold()
        if any(marker in normalized for marker in PLACEHOLDER_MARKERS):
            failures.append(f"{name}: 예시·placeholder 값을 사용할 수 없습니다.")
            continue

        validated[name] = value

    reverse_index: dict[str, list[str]] = {}
    for name, value in validated.items():
        reverse_index.setdefault(value, []).append(name)
    for names in reverse_index.values():
        if len(names) > 1:
            failures.append(
                "보안 키는 서로 달라야 합니다: " + ", ".join(sorted(names))
            )

    return failures


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VisionFlow 로컬 보안 구성 사전 검사"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="VisionFlow 저장소 루트",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="검사할 .env 파일 경로. 기본값은 <root>/.env",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    env_path = (
        args.env_file.resolve()
        if args.env_file is not None
        else root / ".env"
    )

    if not env_path.is_file():
        print("VisionFlow configuration preflight: BLOCKED")
        print(f"[FAIL] .env 파일을 찾을 수 없습니다: {env_path}")
        print("Safety: secret values were not printed or written.")
        return 2

    try:
        values, occurrences, syntax_errors = parse_env_file(env_path)
    except OSError as error:
        print("VisionFlow configuration preflight: BLOCKED")
        print(f"[FAIL] .env 파일을 읽을 수 없습니다: {error}")
        print("Safety: secret values were not printed or written.")
        return 2

    failures = validate_security_configuration(
        values,
        occurrences,
        syntax_errors,
    )
    if failures:
        print("VisionFlow configuration preflight: BLOCKED")
        for failure in failures:
            print(f"[FAIL] {failure}")
        print("Safety: secret values were not printed or written.")
        return 1

    print("VisionFlow configuration preflight: PASS")
    print(f"Environment file: {env_path}")
    for name in REQUIRED_SECRET_NAMES:
        print(f"[PASS] {name}: present; length={len(values[name])}")
    print("[PASS] secret-uniqueness: all required keys are distinct")
    print("Safety: secret values were not printed or written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
