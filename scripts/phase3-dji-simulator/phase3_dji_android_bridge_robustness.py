#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "VisionFlow Phase 3 DJI Android Bridge H265, reconnect, "
            "and decoded-frame backpressure robustness gate."
        )
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--image",
        default="visionflow-ai-server:phase3-android-bridge-v1",
    )
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    ai_root = root / "03_ai-server" / "visionflow-ai"
    evidence_dir = (
        root
        / "artifacts"
        / "phase3-dji-android-bridge-robustness"
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

        steps.append(
            run_step(
                label="Android Bridge test image exists",
                command=[
                    "docker",
                    "image",
                    "inspect",
                    args.image,
                ],
                cwd=root,
            )
        )

        mount = f"{ai_root}:/workspace:ro"
        repository_mount = f"{root}:/repo:ro"
        steps.append(
            run_step(
                label="H265 / reconnect / backpressure robustness",
                command=[
                    "docker",
                    "run",
                    "--rm",
                    "-e",
                    "PYTHONPATH=/workspace",
                    "-e",
                    "VISIONFLOW_REQUIRE_FFMPEG_TEST=1",
                    "-e",
                    "VISIONFLOW_REPOSITORY_ROOT=/repo",
                    "-v",
                    repository_mount,
                    "-v",
                    mount,
                    "-w",
                    "/workspace",
                    args.image,
                    "python",
                    "-m",
                    "pytest",
                    "tests/test_dji_android_bridge_robustness.py",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                ],
                cwd=root,
            )
        )

        steps.append(
            run_step(
                label="Base DJI encoded ingress regression",
                command=[
                    "docker",
                    "run",
                    "--rm",
                    "-e",
                    "PYTHONPATH=/workspace",
                    "-e",
                    "VISIONFLOW_REQUIRE_FFMPEG_TEST=1",
                    "-e",
                    "VISIONFLOW_REPOSITORY_ROOT=/repo",
                    "-v",
                    repository_mount,
                    "-v",
                    mount,
                    "-w",
                    "/workspace",
                    args.image,
                    "python",
                    "-m",
                    "pytest",
                    "tests/test_dji_android_bridge_ingress.py",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                ],
                cwd=root,
            )
        )

        status = "PASS"
        print("")
        print(
            "=== PHASE 3 DJI ANDROID BRIDGE ROBUSTNESS: PASS ==="
        )
        print("h265=PASS")
        print("decoderReconnect=PASS")
        print("decodedFrameBackpressure=PASS")
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
            "gate": "phase3-dji-android-bridge-robustness",
            "status": status,
            "completedAt": utc_now(),
            "h265": status,
            "decoderReconnect": status,
            "decodedFrameBackpressure": status,
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
