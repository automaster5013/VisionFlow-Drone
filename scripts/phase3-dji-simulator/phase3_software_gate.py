#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class GateStep:
    name: str
    command: tuple[str, ...]


def _utf8_child_environment() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _configure_stdout_for_pipe() -> None:
    if sys.stdout.isatty():
        return

    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")


def _console_write(text: str) -> None:
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        safe = (
            text.encode(encoding, errors="replace")
            .decode(encoding, errors="replace")
        )
        sys.stdout.write(safe)
        sys.stdout.flush()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def resolve(root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "VisionFlow Phase 3 software-only DJI gate: simulator, "
            "regression, PPE fixture, DJI_LIVE replay, AI full tests."
        )
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--drone-id", type=int, default=1)
    parser.add_argument(
        "--backend-url",
        default="http://127.0.0.1:8080",
    )
    parser.add_argument(
        "--fixture-video",
        default=(
            "artifacts/phase3-dji-fixture/"
            "phase3-ppe-trigger.mp4"
        ),
    )
    parser.add_argument("--replay-max-frames", type=int, default=300)
    parser.add_argument(
        "--evidence-dir",
        default="artifacts/phase3-software-gate",
    )
    return parser.parse_args()


def require_prerequisites(root: Path) -> None:
    scripts = root / "scripts" / "phase3-dji-simulator"
    required = [
        scripts / "phase3_dji_simulator.py",
        scripts / "phase3_dji_regression.py",
        scripts / "phase3_ppe_fixture_builder.py",
        scripts / "phase3_dji_video_replay.py",
        root / "03_ai-server" / "visionflow-ai" / "tests",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(
            "Phase 3 Gate prerequisite missing: "
            + ", ".join(missing)
        )


def ai_test_command(root: Path) -> tuple[str, ...]:
    ai_root = root / "03_ai-server" / "visionflow-ai"
    return (
        "docker",
        "run",
        "--rm",
        "-e",
        "PYTHONPATH=/workspace",
        "-v",
        f"{ai_root}:/workspace:ro",
        "-w",
        "/workspace",
        "visionflow-ai-server",
        "python",
        "-m",
        "pytest",
        "tests",
        "-q",
        "-p",
        "no:cacheprovider",
    )


def build_steps(
    *,
    root: Path,
    backend_url: str,
    drone_id: int,
    fixture_video: Path,
    replay_max_frames: int,
) -> list[GateStep]:
    scripts = root / "scripts" / "phase3-dji-simulator"
    python = sys.executable

    return [
        GateStep(
            "Git diff whitespace check",
            ("git", "diff", "--check"),
        ),
        GateStep(
            "DJI telemetry/event simulator E2E",
            (
                python,
                str(scripts / "phase3_dji_simulator.py"),
                "--repo-root",
                str(root),
                "--backend-url",
                backend_url,
                "--drone-id",
                str(drone_id),
            ),
        ),
        GateStep(
            "DJI simulator regression",
            (
                python,
                str(scripts / "phase3_dji_regression.py"),
                "--repo-root",
                str(root),
                "--backend-url",
                backend_url,
                "--drone-id",
                str(drone_id),
            ),
        ),
        GateStep(
            "PPE deterministic fixture",
            (
                python,
                str(scripts / "phase3_ppe_fixture_builder.py"),
                "--repo-root",
                str(root),
            ),
        ),
        GateStep(
            "DJI_LIVE video replay E2E",
            (
                python,
                str(scripts / "phase3_dji_video_replay.py"),
                "--repo-root",
                str(root),
                "--backend-url",
                backend_url,
                "--drone-id",
                str(drone_id),
                "--video",
                str(fixture_video),
                "--max-frames",
                str(replay_max_frames),
            ),
        ),
        GateStep(
            "AI full test suite",
            ai_test_command(root),
        ),
    ]


def run_step(
    *,
    step: GateStep,
    cwd: Path,
    log_path: Path,
) -> tuple[int, float]:
    print("")
    print(f"=== {step.name} ===")
    print("[CMD] " + subprocess.list2cmdline(step.command))
    started = time.perf_counter()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as log:
        process = subprocess.Popen(
            step.command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_utf8_child_environment(),
        )
        assert process.stdout is not None

        for line in process.stdout:
            _console_write(line)
            log.write(line)

        return_code = process.wait()

    elapsed = time.perf_counter() - started
    marker = "PASS" if return_code == 0 else "FAIL"
    print(
        f"[{marker}] {step.name} - "
        f"exit={return_code}, {elapsed:.2f}s"
    )
    return return_code, elapsed


def write_summary(
    *,
    path: Path,
    started_at: str,
    status: str,
    backend_url: str,
    drone_id: int,
    fixture_video: Path,
    results: list[dict[str, object]],
) -> None:
    payload = {
        "gate": "phase3-software-only-dji",
        "status": status,
        "startedAt": started_at,
        "completedAt": utc_now(),
        "backendUrl": backend_url,
        "droneId": drone_id,
        "fixtureVideo": str(fixture_video),
        "hardwareDji": "SKIPPED",
        "aws": "SKIPPED",
        "steps": results,
        "passed": sum(
            1 for item in results if item["status"] == "PASS"
        ),
        "failed": sum(
            1 for item in results if item["status"] == "FAIL"
        ),
        "skipped": sum(
            1 for item in results if item["status"] == "SKIPPED"
        ),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    _configure_stdout_for_pipe()
    args = parse_args()
    root = Path(args.repo_root).resolve()
    backend_url = args.backend_url.rstrip("/")
    fixture_video = resolve(root, args.fixture_video)
    evidence_root = resolve(root, args.evidence_dir)

    if args.drone_id < 1:
        print("[FAIL] --drone-id는 1 이상이어야 합니다.")
        return 2
    if args.replay_max_frames <= 0:
        print("[FAIL] --replay-max-frames는 1 이상이어야 합니다.")
        return 2

    try:
        require_prerequisites(root)
    except RuntimeError as error:
        print(f"[FAIL] {error}")
        return 2

    fixture_video.parent.mkdir(parents=True, exist_ok=True)

    gate_run_id = make_run_id()
    run_dir = evidence_root / gate_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_path = run_dir / "summary.json"
    started_at = utc_now()

    print("=== VISIONFLOW PHASE 3 SOFTWARE GATE ===")
    print(f"runId={gate_run_id}")
    print(f"root={root}")
    print(f"backend={backend_url}")
    print(f"droneId={args.drone_id}")
    print("hardwareDJI=SKIPPED")
    print("aws=SKIPPED")

    steps = build_steps(
        root=root,
        backend_url=backend_url,
        drone_id=args.drone_id,
        fixture_video=fixture_video,
        replay_max_frames=args.replay_max_frames,
    )

    results: list[dict[str, object]] = []
    failed = False

    for index, step in enumerate(steps, start=1):
        if failed:
            results.append(
                {
                    "name": step.name,
                    "status": "SKIPPED",
                    "exitCode": None,
                    "durationSeconds": 0.0,
                    "log": None,
                }
            )
            continue

        log_path = run_dir / f"{index:02d}.log"
        try:
            return_code, elapsed = run_step(
                step=step,
                cwd=root,
                log_path=log_path,
            )
        except FileNotFoundError as error:
            return_code = 127
            elapsed = 0.0
            log_path.write_text(
                str(error) + "\n",
                encoding="utf-8",
            )

        status = "PASS" if return_code == 0 else "FAIL"
        results.append(
            {
                "name": step.name,
                "status": status,
                "exitCode": return_code,
                "durationSeconds": round(elapsed, 3),
                "log": str(log_path),
            }
        )
        if return_code != 0:
            failed = True

    overall = "FAIL" if failed else "PASS"
    write_summary(
        path=summary_path,
        started_at=started_at,
        status=overall,
        backend_url=backend_url,
        drone_id=args.drone_id,
        fixture_video=fixture_video,
        results=results,
    )

    print("")
    print("=== PHASE 3 SOFTWARE GATE RESULT ===")
    for item in results:
        print(f"{item['status']:7} {item['name']}")
    print(f"evidence={summary_path}")
    print(f"RESULT={overall}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
