#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


def read_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    return text, newline


def write_text(path: Path, text: str, newline: str) -> None:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    path.write_bytes(normalized.replace("\n", newline).encode("utf-8"))


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: 기준 문자열 발견 횟수={count}")
    return text.replace(old, new, 1)


def set_env(text: str, name: str, value: str) -> str:
    lines = text.splitlines()
    replacement = f"{name}={value}"
    for i, line in enumerate(lines):
        if line.startswith(f"{name}="):
            lines[i] = replacement
            break
    else:
        lines.append(replacement)
    return "\n".join(lines) + "\n"


def make_backup(root: Path, files: list[Path]) -> Path:
    backup = root / "artifacts" / "patch-backups" / f"event-gate-{datetime.now():%Y%m%d-%H%M%S}"
    backup.mkdir(parents=True)
    items = []
    for src in files:
        dst = backup / (src.name + ".bak")
        shutil.copy2(src, dst)
        items.append({"source": str(src), "backup": str(dst)})
    (backup / "manifest.json").write_text(
        json.dumps({"files": items}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return backup


def restore(backup: Path) -> None:
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8-sig"))
    for item in manifest["files"]:
        shutil.copy2(item["backup"], item["source"])
        print(f"복원 완료: {item['source']}")


def latest_backup(root: Path) -> Path:
    base = root / "artifacts" / "patch-backups"
    found = sorted(
        [p for p in base.glob("event-gate-*") if p.is_dir()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not found:
        raise RuntimeError(f"백업을 찾을 수 없습니다: {base}")
    return found[0]


def patch_config(path: Path) -> None:
    text, nl = read_text(path)

    if "event_min_consecutive_frames: int" not in text:
        text = replace_once(
            text,
            "    report_queue_capacity: int\n    snapshot_enabled: bool\n",
            "    report_queue_capacity: int\n"
            "    event_min_consecutive_frames: int\n"
            "    event_cooldown_seconds: float\n"
            "    snapshot_enabled: bool\n",
            "config.py 필드",
        )

    if '"AI_EVENT_MIN_CONSECUTIVE_FRAMES"' not in text:
        text = replace_once(
            text,
            '            report_queue_capacity=_read_int(\n'
            '                "AI_REPORT_QUEUE_CAPACITY",\n'
            '                200,\n'
            '            ),\n'
            '            snapshot_enabled=_read_bool("AI_SNAPSHOT_ENABLED", True),\n',
            '            report_queue_capacity=_read_int(\n'
            '                "AI_REPORT_QUEUE_CAPACITY",\n'
            '                200,\n'
            '            ),\n'
            '            event_min_consecutive_frames=_read_int(\n'
            '                "AI_EVENT_MIN_CONSECUTIVE_FRAMES",\n'
            '                5,\n'
            '            ),\n'
            '            event_cooldown_seconds=_read_float(\n'
            '                "AI_EVENT_COOLDOWN_SECONDS",\n'
            '                10.0,\n'
            '            ),\n'
            '            snapshot_enabled=_read_bool("AI_SNAPSHOT_ENABLED", True),\n',
            "config.py 환경변수",
        )

    if "if self.event_min_consecutive_frames <= 0:" not in text:
        text = replace_once(
            text,
            "        if not 1 <= self.snapshot_jpeg_quality <= 100:\n",
            '        if self.event_min_consecutive_frames <= 0:\n'
            '            raise ValueError(\n'
            '                "AI_EVENT_MIN_CONSECUTIVE_FRAMES는 1 이상이어야 합니다."\n'
            '            )\n\n'
            '        if self.event_cooldown_seconds < 0:\n'
            '            raise ValueError(\n'
            '                "AI_EVENT_COOLDOWN_SECONDS는 0 이상이어야 합니다."\n'
            '            )\n\n'
            '        if not 1 <= self.snapshot_jpeg_quality <= 100:\n',
            "config.py 검증",
        )

    write_text(path, text, nl)


def patch_pipeline(path: Path) -> None:
    text, nl = read_text(path)

    if "from collections import Counter" not in text:
        text = replace_once(
            text,
            "import json\nfrom pathlib import Path\n",
            "import json\nimport time\nfrom collections import Counter\n"
            "from dataclasses import dataclass\nfrom pathlib import Path\n",
            "pipeline.py import",
        )

    if "from app.domain import InferencePacket" not in text:
        text = replace_once(
            text,
            "from app.inference import YoloDetector\n",
            "from app.domain import InferencePacket\nfrom app.inference import YoloDetector\n",
            "pipeline.py domain import",
        )

    if "class _EventGateState:" not in text:
        text = replace_once(
            text,
            "class InferencePipeline:\n",
            "EventSignature = tuple[tuple[int, int], ...]\n\n\n"
            "@dataclass(slots=True)\n"
            "class _EventGateState:\n"
            "    pending_signature: EventSignature | None = None\n"
            "    consecutive_frames: int = 0\n"
            "    empty_frames: int = 0\n"
            "    last_reported_signature: EventSignature | None = None\n"
            "    last_reported_at: float | None = None\n\n\n"
            "class InferencePipeline:\n",
            "pipeline.py state",
        )

    if "event_min_consecutive_frames: int," not in text:
        text = replace_once(
            text,
            "        snapshot_enabled: bool,\n"
            "        snapshot_jpeg_quality: int,\n"
            "        performance_monitor: InferencePerformanceMonitor | None = None,\n",
            "        snapshot_enabled: bool,\n"
            "        snapshot_jpeg_quality: int,\n"
            "        event_min_consecutive_frames: int,\n"
            "        event_cooldown_seconds: float,\n"
            "        performance_monitor: InferencePerformanceMonitor | None = None,\n",
            "pipeline.py args",
        )

    if "self._event_min_consecutive_frames = event_min_consecutive_frames" not in text:
        text = replace_once(
            text,
            "        self._snapshot_enabled = snapshot_enabled\n"
            "        self._snapshot_jpeg_quality = snapshot_jpeg_quality\n"
            "        self._performance_monitor = performance_monitor\n",
            "        self._snapshot_enabled = snapshot_enabled\n"
            "        self._snapshot_jpeg_quality = snapshot_jpeg_quality\n"
            "        self._event_min_consecutive_frames = event_min_consecutive_frames\n"
            "        self._event_cooldown_seconds = event_cooldown_seconds\n"
            "        self._event_gate_states: dict[\n"
            "            tuple[str, str, int],\n"
            "            _EventGateState,\n"
            "        ] = {}\n"
            "        self._performance_monitor = performance_monitor\n",
            "pipeline.py fields",
        )

    if "if self._should_report_event(inference):" not in text:
        pattern = r"(?m)^(?P<indent>[ \t]*)if inference\.detections:[ \t]*$"
        matches = list(re.finditer(pattern, text))
        if len(matches) != 1:
            raise RuntimeError(
                f"pipeline.py 이벤트 조건 발견 횟수={len(matches)}"
            )
        text = re.sub(
            pattern,
            r"\g<indent>if self._should_report_event(inference):",
            text,
            count=1,
        )

    if "def _should_report_event(" not in text:
        method = '''    def _should_report_event(
        self,
        inference: InferencePacket,
    ) -> bool:
        key = (
            inference.frame.source_id,
            inference.frame.session_id,
            inference.frame.drone_id,
        )

        if not inference.detections:
            state = self._event_gate_states.get(key)
            if state is None:
                return False

            state.empty_frames += 1
            state.pending_signature = None
            state.consecutive_frames = 0

            if state.empty_frames >= self._event_min_consecutive_frames:
                self._event_gate_states.pop(key, None)

            return False

        state = self._event_gate_states.setdefault(key, _EventGateState())
        state.empty_frames = 0

        counts = Counter(d.class_id for d in inference.detections)
        signature: EventSignature = tuple(sorted(counts.items()))

        if state.pending_signature == signature:
            state.consecutive_frames += 1
        else:
            state.pending_signature = signature
            state.consecutive_frames = 1

        if state.consecutive_frames < self._event_min_consecutive_frames:
            return False

        now = time.monotonic()
        state_changed = state.last_reported_signature != signature
        cooldown_elapsed = (
            state.last_reported_at is None
            or now - state.last_reported_at >= self._event_cooldown_seconds
        )

        if not state_changed and not cooldown_elapsed:
            return False

        state.last_reported_signature = signature
        state.last_reported_at = now
        return True

'''
        text = replace_once(
            text,
            "    def _create_writer(",
            method + "    def _create_writer(",
            "pipeline.py gate method",
        )

    write_text(path, text, nl)


def patch_main(path: Path) -> None:
    text, nl = read_text(path)
    if "event_min_consecutive_frames=(" not in text:
        text = replace_once(
            text,
            "        snapshot_enabled=settings.snapshot_enabled,\n"
            "        snapshot_jpeg_quality=settings.snapshot_jpeg_quality,\n"
            "        performance_monitor=performance_monitor,\n",
            "        snapshot_enabled=settings.snapshot_enabled,\n"
            "        snapshot_jpeg_quality=settings.snapshot_jpeg_quality,\n"
            "        event_min_consecutive_frames=(\n"
            "            settings.event_min_consecutive_frames\n"
            "        ),\n"
            "        event_cooldown_seconds=(\n"
            "            settings.event_cooldown_seconds\n"
            "        ),\n"
            "        performance_monitor=performance_monitor,\n",
            "main.py args",
        )
    write_text(path, text, nl)


def apply(root: Path) -> None:
    config = root / "03_ai-server/visionflow-ai/app/config.py"
    pipeline = root / "03_ai-server/visionflow-ai/app/pipeline.py"
    main = root / "03_ai-server/visionflow-ai/app/main.py"
    dotenv = root / ".env"
    files = [config, pipeline, main, dotenv]

    missing = [str(p) for p in files if not p.is_file()]
    if missing:
        raise RuntimeError("필수 파일이 없습니다:\n" + "\n".join(missing))

    backup = make_backup(root, files)
    print(f"백업 완료: {backup}")
    try:
        patch_config(config)
        print("패치 완료: config.py")
        patch_pipeline(pipeline)
        print("패치 완료: pipeline.py")
        patch_main(main)
        print("패치 완료: main.py")

        env_text, env_nl = read_text(dotenv)
        env_text = set_env(env_text, "AI_EVENT_MIN_CONSECUTIVE_FRAMES", "5")
        env_text = set_env(env_text, "AI_EVENT_COOLDOWN_SECONDS", "10")
        write_text(dotenv, env_text, env_nl)
        print("설정 완료: .env")

        for path in (config, pipeline, main):
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            print(f"문법 검증 완료: {path.name}")
    except Exception:
        print("패치 실패: 원본 자동 복원", file=sys.stderr)
        restore(backup)
        raise

    print("\n패치가 완료됐습니다.")
    print(f"백업 위치: {backup}")
    print("\n다음 명령:")
    print(f'  cd /d "{root}"')
    print("  docker compose config --services")
    print("  docker compose up -d --build ai-server")
    print('  docker ps --format "table {{.Names}}\\t{{.Status}}"')
    print("  docker logs visionflow-ai --tail 100")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=r"C:\VisionFlow-Drone")
    parser.add_argument("--rollback", nargs="?", const="LATEST")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()

    try:
        if args.rollback is not None:
            backup = latest_backup(root) if args.rollback == "LATEST" else Path(args.rollback)
            restore(backup)
            print("\n롤백 완료")
        else:
            apply(root)
    except Exception as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
