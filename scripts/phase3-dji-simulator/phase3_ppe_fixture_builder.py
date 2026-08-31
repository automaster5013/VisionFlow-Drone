#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class FixtureError(RuntimeError):
    pass


SHWD_RAW_BASE = (
    "https://raw.githubusercontent.com/"
    "njvisionpower/Safety-Helmet-Wearing-Dataset/master/image"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download a small public helmet/no-helmet demo set, scan it with "
            "the current VisionFlow models, and build a deterministic PPE "
            "trigger MP4 fixture."
        )
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument(
        "--output-dir",
        default="artifacts/phase3-dji-fixture",
    )
    parser.add_argument("--image", default="visionflow-ai-server")
    parser.add_argument("--duration-seconds", type=float, default=10.0)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--confidence", type=float, default=0.35)
    return parser.parse_args()


def download(url: str, path: Path) -> None:
    if path.is_file() and path.stat().st_size > 0:
        return

    request = Request(
        url,
        headers={"User-Agent": "VisionFlow-Drone-Phase3-Fixture/1.0"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = response.read()
    except (HTTPError, URLError, TimeoutError) as error:
        raise FixtureError(f"download failed: {url}: {error}") from error

    if len(payload) < 1024:
        raise FixtureError(
            f"downloaded candidate is unexpectedly small: {url}"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def docker_scan_command(
    *,
    root: Path,
    output_dir: Path,
    image: str,
    duration_seconds: float,
    fps: float,
    confidence: float,
) -> list[str]:
    container_script = (
        "/workspace/scripts/phase3-dji-simulator/"
        "phase3_ppe_fixture_container.py"
    )
    return [
        "docker",
        "run",
        "--rm",
        "--gpus",
        "all",
        "-e",
        "PYTHONPATH=/workspace/03_ai-server/visionflow-ai",
        "-v",
        f"{root}:/workspace:ro",
        "-v",
        f"{output_dir}:/fixture:rw",
        "-w",
        "/workspace/03_ai-server/visionflow-ai",
        image,
        "python",
        container_script,
        "--input-dir",
        "/fixture/shwd",
        "--output-video",
        "/fixture/phase3-ppe-trigger.mp4",
        "--report",
        "/fixture/scan-report.json",
        "--track-model",
        "/workspace/03_ai-server/visionflow-ai/models/yolo26m.pt",
        "--ppe-model",
        "/workspace/03_ai-server/visionflow-ai/models/ppe-yolo26m-best.pt",
        "--duration-seconds",
        str(duration_seconds),
        "--fps",
        str(fps),
        "--confidence",
        str(confidence),
    ]


def run(command: list[str]) -> None:
    result = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise FixtureError(
            f"fixture scanner exited with code {result.returncode}"
        )


def main() -> int:
    args = parse_args()
    root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir = output_dir.resolve()

    if args.duration_seconds < 3.0:
        print(
            "[FAIL] --duration-seconds는 최소 3초 이상이어야 합니다.",
            file=sys.stderr,
        )
        return 2
    if args.fps <= 0:
        print("[FAIL] --fps는 양수여야 합니다.", file=sys.stderr)
        return 2
    if not 0.0 < args.confidence <= 1.0:
        print(
            "[FAIL] --confidence는 0 초과 1 이하여야 합니다.",
            file=sys.stderr,
        )
        return 2

    source_dir = output_dir / "shwd"
    source_dir.mkdir(parents=True, exist_ok=True)

    print("[STEP] SHWD demo candidates 준비")
    for index in range(1, 11):
        url = f"{SHWD_RAW_BASE}/{index}.jpg"
        destination = source_dir / f"{index}.jpg"
        try:
            download(url, destination)
        except FixtureError as error:
            print(
                f"[WARN] candidate {index}.jpg 건너뜀 - {error}",
                file=sys.stderr,
            )

    downloaded = sorted(source_dir.glob("*.jpg"))
    if len(downloaded) < 3:
        print(
            f"[FAIL] usable candidate images={len(downloaded)}; 최소 3장 필요",
            file=sys.stderr,
        )
        return 1
    print(f"[PASS] SHWD demo candidates - images={len(downloaded)}")

    print("[STEP] 현재 YOLO26m + PPE 모델로 후보 스캔 및 MP4 생성")
    try:
        run(
            docker_scan_command(
                root=root,
                output_dir=output_dir,
                image=args.image,
                duration_seconds=args.duration_seconds,
                fps=args.fps,
                confidence=args.confidence,
            )
        )
    except (FixtureError, FileNotFoundError) as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1

    report_path = output_dir / "scan-report.json"
    video_path = output_dir / "phase3-ppe-trigger.mp4"
    if not report_path.is_file():
        print(f"[FAIL] scan report 없음: {report_path}", file=sys.stderr)
        return 1
    if not video_path.is_file() or video_path.stat().st_size <= 0:
        print(f"[FAIL] fixture MP4 없음: {video_path}", file=sys.stderr)
        return 1

    report = json.loads(report_path.read_text(encoding="utf-8"))
    selected = report.get("selected") or {}
    print("")
    print("=== PHASE 3 PPE VIDEO FIXTURE: PASS ===")
    print(f"selected={selected.get('file')}")
    print(f"personTracks={selected.get('personTracks')}")
    print(f"headNoHelmetTracks={selected.get('headNoHelmetTracks')}")
    print(f"helmetTracks={selected.get('helmetTracks')}")
    print(f"video={video_path}")
    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
