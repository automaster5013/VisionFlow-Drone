#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DEFAULT = r"C:\VisionFlow-Drone"
PIPELINE_REL = Path("03_ai-server/visionflow-ai/app/pipeline.py")
SMOKE_REL = Path("scripts/visionflow_ai_e2e_smoke.py")
BACKUP_ROOT_REL = Path("artifacts/event-gate-hardening-backups")
MARKER = "# VisionFlow hard cooldown gate v2"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_source(path: Path) -> tuple[str, str, bool]:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), newline, has_bom


def write_source(path: Path, text: str, newline: str, has_bom: bool) -> None:
    normalized = text.replace("\r\n", "\n")
    if newline != "\n":
        normalized = normalized.replace("\n", newline)
    payload = normalized.encode("utf-8")
    if has_bom:
        payload = b"\xef\xbb\xbf" + payload
    path.write_bytes(payload)


def replace_exact_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, actual={count}")
    return text.replace(old, new, 1)


def replace_regex_once(
    text: str,
    pattern: str,
    replacement: str,
    label: str,
    *,
    flags: int = 0,
) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one regex match, actual={count}")
    return updated


def make_backup(root: Path, files: list[Path]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = root / BACKUP_ROOT_REL / f"event-gate-hardening-{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    manifest_files: list[dict[str, str]] = []
    for source in files:
        relative = source.relative_to(root)
        target = backup_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        manifest_files.append(
            {
                "relativePath": str(relative).replace("\\", "/"),
                "sha256": sha256(source),
            }
        )

    manifest = {
        "schemaVersion": 1,
        "createdAt": utc_now(),
        "root": str(root),
        "files": manifest_files,
    }
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return backup_dir


def latest_backup(root: Path) -> Path:
    backup_root = root / BACKUP_ROOT_REL
    candidates = sorted(
        (path for path in backup_root.glob("event-gate-hardening-*") if path.is_dir()),
        reverse=True,
    )
    if not candidates:
        raise RuntimeError(f"No hardening backup was found: {backup_root}")
    return candidates[0]


def restore(root: Path, backup_dir: Path) -> None:
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"Backup manifest was not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest.get("files", []):
        relative = Path(item["relativePath"])
        source = backup_dir / relative
        target = root / relative
        if not source.is_file():
            raise RuntimeError(f"Backup file was not found: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"Restored: {target}")


def patch_pipeline(path: Path) -> bool:
    text, newline, has_bom = read_source(path)
    if MARKER in text:
        print(f"Already hardened: {path}")
        return False

    if "def _should_report_event(" not in text:
        raise RuntimeError(
            "pipeline.py does not contain _should_report_event(). "
            "Apply the original 5-frame/10-second gate patch first."
        )

    text = re.sub(
        r"(?m)^from collections import Counter[ \t]*\n",
        "",
        text,
        count=1,
    )
    text = re.sub(
        r"(?m)^EventSignature\s*=\s*tuple\[tuple\[int,\s*int\],\s*\.\.\.\][ \t]*\n+",
        "",
        text,
        count=1,
    )

    state_pattern = (
        r"(?ms)^@dataclass\(slots=True\)\n"
        r"class _EventGateState:\n"
        r".*?"
        r"^class InferencePipeline:"
    )
    state_replacement = '''@dataclass(slots=True)
class _EventGateState:
    consecutive_frames: int = 0
    last_reported_at: float | None = None
    last_seen_at: float = 0.0


class InferencePipeline:'''
    text = replace_regex_once(
        text,
        state_pattern,
        state_replacement,
        "pipeline.py gate state",
        flags=re.MULTILINE | re.DOTALL,
    )

    ttl_field = (
        "        self._event_gate_state_ttl_seconds = max(\n"
        "            60.0,\n"
        "            event_cooldown_seconds * 6.0,\n"
        "        )\n"
    )
    if "self._event_gate_state_ttl_seconds" not in text:
        state_map_pattern = (
            r"(?ms)(        self\._event_gate_states: dict\[\n"
            r"            tuple\[str, str, int\],\n"
            r"            _EventGateState,\n"
            r"        \] = \{\}\n)"
        )
        text = replace_regex_once(
            text,
            state_map_pattern,
            r"\1" + ttl_field,
            "pipeline.py gate TTL field",
            flags=re.MULTILINE | re.DOTALL,
        )

    method_pattern = (
        r"(?ms)^    def _should_report_event\(\n"
        r".*?"
        r"^    def _create_writer\("
    )
    method_replacement = '''    # VisionFlow hard cooldown gate v2
    def _should_report_event(
        self,
        inference: InferencePacket,
    ) -> bool:
        now = time.monotonic()
        key = (
            inference.frame.source_id,
            inference.frame.session_id,
            inference.frame.drone_id,
        )

        self._prune_event_gate_states(now, keep_key=key)

        state = self._event_gate_states.setdefault(key, _EventGateState())
        state.last_seen_at = now

        if not inference.detections:
            state.consecutive_frames = 0
            return False

        state.consecutive_frames += 1
        if state.consecutive_frames < self._event_min_consecutive_frames:
            return False

        if (
            state.last_reported_at is not None
            and now - state.last_reported_at < self._event_cooldown_seconds
        ):
            return False

        # 탐지 클래스/개수 변화와 관계없이 스트림별 절대 쿨다운을 적용합니다.
        state.last_reported_at = now
        return True

    def _prune_event_gate_states(
        self,
        now: float,
        *,
        keep_key: tuple[str, str, int],
    ) -> None:
        stale_keys = [
            key
            for key, state in self._event_gate_states.items()
            if key != keep_key
            and now - state.last_seen_at >= self._event_gate_state_ttl_seconds
        ]
        for key in stale_keys:
            self._event_gate_states.pop(key, None)

    def _create_writer('''
    text = replace_regex_once(
        text,
        method_pattern,
        method_replacement,
        "pipeline.py gate method",
        flags=re.MULTILINE | re.DOTALL,
    )

    ast.parse(text, filename=str(path))
    write_source(path, text, newline, has_bom)
    print(f"Hardened: {path}")
    return True


def patch_smoke_test(path: Path) -> bool:
    text, newline, has_bom = read_source(path)
    changed = False

    if 'parser.add_argument("--expected-events"' not in text:
        anchor = '    parser.add_argument("--wait-seconds", type=int, default=30)\n'
        insertion = (
            anchor
            + '    parser.add_argument("--expected-events", type=int, default=1)\n'
        )
        text = replace_exact_once(
            text,
            anchor,
            insertion,
            "smoke test expected-events argument",
        )
        changed = True

    validation_anchor = '    if shutil.which("docker") is None:\n'
    if "args.expected_events <= 0" not in text:
        validation = (
            "    if args.expected_events <= 0:\n"
            '        raise RuntimeError("--expected-events must be at least 1.")\n\n'
        )
        text = replace_exact_once(
            text,
            validation_anchor,
            validation + validation_anchor,
            "smoke test expected-events validation",
        )
        changed = True

    old_poll = '        if stats["events"] >= 1 and stats["snapshots"] >= 1:\n'
    new_poll = (
        '        if (\n'
        '            stats["events"] >= args.expected_events\n'
        '            and stats["snapshots"] >= args.expected_events\n'
        '        ):\n'
    )
    if old_poll in text:
        text = replace_exact_once(text, old_poll, new_poll, "smoke test poll")
        changed = True

    replacements = [
        (
            '    if stats.get("events") != 1:\n',
            '    if stats.get("events") != args.expected_events:\n',
            "event count condition",
        ),
        (
            '            f"Expected exactly 1 event, actual={stats.get(\'events\')}. "\n',
            '            f"Expected exactly {args.expected_events} event(s), "\n'
            '            f"actual={stats.get(\'events\')}. "\n',
            "event count message",
        ),
        (
            '    if stats.get("alerts") != 1:\n',
            '    if stats.get("alerts") != args.expected_events:\n',
            "alert count condition",
        ),
        (
            '        problems.append(f"Expected exactly 1 alert, actual={stats.get(\'alerts\')}.")\n',
            '        problems.append(\n'
            '            f"Expected exactly {args.expected_events} alert(s), "\n'
            '            f"actual={stats.get(\'alerts\')}."\n'
            '        )\n',
            "alert count message",
        ),
        (
            '    if stats.get("snapshots") != 1:\n',
            '    if stats.get("snapshots") != args.expected_events:\n',
            "snapshot count condition",
        ),
        (
            '        problems.append(f"Expected exactly 1 snapshot, actual={stats.get(\'snapshots\')}.")\n',
            '        problems.append(\n'
            '            f"Expected exactly {args.expected_events} snapshot(s), "\n'
            '            f"actual={stats.get(\'snapshots\')}."\n'
            '        )\n',
            "snapshot count message",
        ),
        (
            '    if len(file_checks) != 1 or not all(\n',
            '    if len(file_checks) != args.expected_events or not all(\n',
            "snapshot file count condition",
        ),
        (
            '            "expectedEvents": 1,\n'
            '            "expectedAlerts": 1,\n'
            '            "expectedSnapshots": 1,\n',
            '            "expectedEvents": args.expected_events,\n'
            '            "expectedAlerts": args.expected_events,\n'
            '            "expectedSnapshots": args.expected_events,\n',
            "report expected counts",
        ),
    ]

    for old, new, label in replacements:
        if old in text:
            text = replace_exact_once(text, old, new, f"smoke test {label}")
            changed = True

    if changed:
        ast.parse(text, filename=str(path))
        write_source(path, text, newline, has_bom)
        print(f"Enhanced: {path}")
    else:
        print(f"Already enhanced: {path}")

    return changed


def apply(root: Path) -> int:
    pipeline = root / PIPELINE_REL
    smoke = root / SMOKE_REL
    required = [pipeline, smoke]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("Required files are missing:\n" + "\n".join(missing))

    backup = make_backup(root, required)
    print(f"Backup: {backup}")

    try:
        pipeline_changed = patch_pipeline(pipeline)
        smoke_changed = patch_smoke_test(smoke)
    except Exception:
        print("Patch failed. Restoring original files.", file=sys.stderr)
        restore(root, backup)
        raise

    manifest_path = backup / "patched-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "patchedAt": utc_now(),
                "pipelineChanged": pipeline_changed,
                "smokeTestChanged": smoke_changed,
                "patchedFiles": [
                    {
                        "relativePath": str(path.relative_to(root)).replace("\\", "/"),
                        "sha256": sha256(path),
                    }
                    for path in required
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("")
    print("Patch completed.")
    print(f"Rollback backup: {backup}")
    print("")
    print("Next commands:")
    print(f'  cd /d "{root}"')
    print(
        "  docker compose -f compose.yaml -f compose.gpu.yaml "
        "-f compose.model.yaml up -d --build ai-server"
    )
    print("  scripts\\run-visionflow-ai-e2e-smoke.bat")
    print(
        "  scripts\\run-visionflow-ai-e2e-smoke.bat "
        "--frames 70 --fps 5 --expected-events 2 --wait-seconds 60"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Harden VisionFlow AI event deduplication so the 10-second cooldown "
            "cannot be bypassed by detection signature changes or short empty periods."
        )
    )
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument("--rollback", nargs="?", const="LATEST")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()

    try:
        if args.rollback is not None:
            backup = latest_backup(root) if args.rollback == "LATEST" else Path(args.rollback)
            restore(root, backup.resolve())
            print(f"Rollback completed: {backup}")
            return 0
        return apply(root)
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
