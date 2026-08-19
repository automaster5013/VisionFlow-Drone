#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


class GateError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_step(
    *,
    label: str,
    command: list[str],
    cwd: Path,
) -> dict[str, object]:
    print("")
    print(f"=== {label} ===")
    print("[CMD] " + subprocess.list2cmdline(command))

    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    status = "PASS" if result.returncode == 0 else "FAIL"
    print(f"[{status}] {label} - exit={result.returncode}")

    if result.returncode != 0:
        raise GateError(
            f"{label} failed with exit={result.returncode}"
        )

    return {
        "name": label,
        "status": status,
        "exitCode": result.returncode,
    }


def windows_command(*parts: str) -> list[str]:
    if os.name == "nt":
        return ["cmd.exe", "/d", "/c", *parts]
    return list(parts)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "VisionFlow Phase 3 DJI Android Bridge software-only "
            "encoded-ingress gate."
        )
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--image",
        default="visionflow-ai-server:phase3-android-bridge-v1",
    )
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    ai_root = root / "03_ai-server" / "visionflow-ai"
    android_root = root / "04_android" / "visionflow-dji-bridge"
    evidence_dir = (
        root
        / "artifacts"
        / "phase3-dji-android-bridge"
        / run_id()
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    summary_path = evidence_dir / "summary.json"

    steps: list[dict[str, object]] = []
    status = "FAIL"

    try:
        steps.append(
            run_step(
                label="Git whitespace check",
                command=[
                    "git",
                    "-C",
                    str(root),
                    "diff",
                    "--check",
                ],
                cwd=root,
            )
        )

        if not args.skip_build:
            steps.append(
                run_step(
                    label="AI image build with FFmpeg",
                    command=[
                        "docker",
                        "build",
                        "-t",
                        args.image,
                        ".",
                    ],
                    cwd=ai_root,
                )
            )

        steps.append(
            run_step(
                label="FFmpeg runtime",
                command=[
                    "docker",
                    "run",
                    "--rm",
                    args.image,
                    "ffmpeg",
                    "-version",
                ],
                cwd=root,
            )
        )

        steps.append(
            run_step(
                label="AI full suite with DJI encoded ingress",
                command=[
                    "docker",
                    "run",
                    "--rm",
                    "-e",
                    "VISIONFLOW_REQUIRE_FFMPEG_TEST=1",
                    args.image,
                    "python",
                    "-m",
                    "pytest",
                    "tests",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                ],
                cwd=root,
            )
        )

        steps.append(
            run_step(
                label="Android DJI Bridge assembleDebug",
                command=windows_command(
                    "gradlew.bat",
                    ":app:assembleDebug",
                ),
                cwd=android_root,
            )
        )

        status = "PASS"
        print("")
        print("=== PHASE 3 DJI ANDROID BRIDGE GATE: PASS ===")
        print("physicalDJI=SKIPPED")
        print("aws=SKIPPED")
        print(f"image={args.image}")
        print(f"evidence={summary_path}")
        return 0

    except (GateError, FileNotFoundError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1

    finally:
        summary = {
            "gate": "phase3-dji-android-bridge",
            "status": status,
            "completedAt": utc_now(),
            "physicalDjiRuntime": "SKIPPED",
            "aws": "SKIPPED",
            "image": args.image,
            "steps": steps,
        }
        summary_path.write_text(
            json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    raise SystemExit(main())
