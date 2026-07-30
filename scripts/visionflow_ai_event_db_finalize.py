#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DEFAULT = r"C:\VisionFlow-Drone"
MYSQL_CONTAINER = "visionflow-mysql"
SERVICE_CONTAINERS = ("visionflow-ai", "visionflow-backend")

SOURCE_ID = "browser-camera-001"
SESSION_IDS = (
    "720f652c-8498-4686-a20d-fb573b7ef562",
    "890614dc-71ff-45ea-bf9a-62177cde072f",
    "a8edd33f-7e44-4e01-93b7-2bdaafff5587",
)
MIN_EVENT_ID = 6943
MAX_EVENT_ID = 140249

EXPECTED_TARGET = {
    "events": 133_307,
    "detections": 333_658,
    "alerts": 133_307,
    "snapshots": 133_306,
    "snapshotBytes": 15_413_065_831,
}
EXPECTED_REMAINING = {
    "events": 6_942,
    "detections": 22_700,
    "alerts": 6_942,
    "snapshots": 6_942,
}

DELETE_TOKEN = "DELETE_133307_EVENTS"
RESTORE_TOKEN = "RESTORE_133307_EVENTS"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def condition(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    sessions = ",".join(f"'{value}'" for value in SESSION_IDS)
    return (
        f"{prefix}source_id='{SOURCE_ID}' AND "
        f"{prefix}session_id IN ({sessions}) AND "
        f"{prefix}id BETWEEN {MIN_EVENT_ID} AND {MAX_EVENT_ID}"
    )


def run(
    args: list[str],
    *,
    input_text: str | None = None,
    stdin_file: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    if input_text is not None and stdin_file is not None:
        raise ValueError("input_text와 stdin_file을 동시에 사용할 수 없습니다.")

    if stdin_file is not None:
        with stdin_file.open("rb") as stream:
            completed = subprocess.run(
                args,
                stdin=stream,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
    else:
        completed = subprocess.run(
            args,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        stdout = completed.stdout
        stderr = completed.stderr

    if completed.returncode != 0:
        raise RuntimeError(
            f"명령 실패({completed.returncode}): {' '.join(args)}\n{stderr}"
        )

    return subprocess.CompletedProcess(
        args=args,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def mysql_query(sql: str) -> str:
    command = (
        'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -D "$MYSQL_DATABASE" '
        '--batch --raw --skip-column-names '
        f"-e {shlex.quote(sql)}"
    )
    return run(
        ["docker", "exec", MYSQL_CONTAINER, "sh", "-lc", command]
    ).stdout


def mysql_import(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"복원 SQL 파일이 없거나 비어 있습니다: {path}")
    command = (
        'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" '
        '-D "$MYSQL_DATABASE" --show-warnings'
    )
    run(
        ["docker", "exec", "-i", MYSQL_CONTAINER, "sh", "-lc", command],
        stdin_file=path,
    )


def parse_counts(output: str, keys: tuple[str, ...]) -> dict[str, int]:
    values = output.strip().split("\t")
    if len(values) != len(keys):
        raise RuntimeError(f"DB 집계 결과 형식 오류: {output!r}")
    return {key: int(value) for key, value in zip(keys, values)}


def target_counts() -> dict[str, int]:
    sql = (
        "SELECT "
        f"(SELECT COUNT(*) FROM ai_inference_event WHERE {condition()}),"
        "(SELECT COUNT(*) FROM ai_detection d "
        "JOIN ai_inference_event e ON e.id=d.event_id "
        f"WHERE {condition('e')}),"
        "(SELECT COUNT(*) FROM ai_alert a "
        "JOIN ai_inference_event e ON e.id=a.event_id "
        f"WHERE {condition('e')}),"
        f"(SELECT COUNT(*) FROM ai_inference_event "
        f"WHERE {condition()} AND snapshot_file_name IS NOT NULL),"
        f"(SELECT COALESCE(SUM(snapshot_size_bytes),0) "
        f"FROM ai_inference_event WHERE {condition()} "
        "AND snapshot_file_name IS NOT NULL);"
    )
    return parse_counts(
        mysql_query(sql),
        ("events", "detections", "alerts", "snapshots", "snapshotBytes"),
    )


def total_counts() -> dict[str, int]:
    sql = (
        "SELECT "
        "(SELECT COUNT(*) FROM ai_inference_event),"
        "(SELECT COUNT(*) FROM ai_detection),"
        "(SELECT COUNT(*) FROM ai_alert),"
        "(SELECT COUNT(*) FROM ai_inference_event "
        "WHERE snapshot_file_name IS NOT NULL);"
    )
    return parse_counts(
        mysql_query(sql),
        ("events", "detections", "alerts", "snapshots"),
    )


def require_equal(actual: dict[str, int], expected: dict[str, int], label: str) -> None:
    if actual != expected:
        raise RuntimeError(
            f"{label} 불일치\n"
            f"예상={json.dumps(expected, ensure_ascii=False)}\n"
            f"실제={json.dumps(actual, ensure_ascii=False)}"
        )


def load_operation(operation: Path) -> dict[str, object]:
    path = operation / "operation.json"
    if not path.is_file():
        raise RuntimeError(f"operation.json이 없습니다: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))

    if data.get("sourceId") != SOURCE_ID:
        raise RuntimeError("operation sourceId가 승인된 값과 다릅니다.")
    if tuple(data.get("sessionIds", [])) != SESSION_IDS:
        raise RuntimeError("operation sessionIds가 승인된 값과 다릅니다.")
    if int(data.get("minEventId", -1)) != MIN_EVENT_ID:
        raise RuntimeError("operation minEventId가 승인된 값과 다릅니다.")
    if int(data.get("maxEventId", -1)) != MAX_EVENT_ID:
        raise RuntimeError("operation maxEventId가 승인된 값과 다릅니다.")

    expected = data.get("expected")
    if expected != EXPECTED_TARGET:
        raise RuntimeError(
            "operation expected 집계가 승인된 값과 다릅니다.\n"
            f"operation={json.dumps(expected, ensure_ascii=False)}"
        )
    return data


def save_operation(operation: Path, data: dict[str, object]) -> None:
    data["updatedAt"] = now_utc()
    (operation / "operation.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_manifest(operation: Path) -> list[dict[str, object]]:
    path = operation / "manifest" / "target-snapshots.csv"
    if not path.is_file():
        raise RuntimeError(f"스냅샷 manifest가 없습니다: {path}")

    rows: list[dict[str, object]] = []
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        for item in csv.DictReader(stream):
            event_id = int(item["event_id"])
            file_name = item["file_name"]
            size_bytes = int(item["size_bytes"])
            if file_name != f"event-{event_id}.jpg":
                raise RuntimeError(
                    f"manifest 이벤트/파일명 불일치: {event_id}/{file_name}"
                )
            rows.append(
                {
                    "event_id": event_id,
                    "session_id": item["session_id"],
                    "file_name": file_name,
                    "size_bytes": size_bytes,
                    "source_path": item["source_path"],
                    "quarantine_path": item["quarantine_path"],
                }
            )

    if len(rows) != EXPECTED_TARGET["snapshots"]:
        raise RuntimeError(f"manifest 파일 수 불일치: {len(rows)}")
    total = sum(int(row["size_bytes"]) for row in rows)
    if total != EXPECTED_TARGET["snapshotBytes"]:
        raise RuntimeError(f"manifest 총 바이트 불일치: {total}")
    return rows


def verify_quarantine(rows: list[dict[str, object]]) -> None:
    total = 0
    for index, row in enumerate(rows, start=1):
        source = Path(str(row["source_path"]))
        quarantine = Path(str(row["quarantine_path"]))
        if source.exists():
            raise RuntimeError(f"원본 위치에 대상 파일이 남아 있습니다: {source}")
        if not quarantine.is_file():
            raise RuntimeError(f"격리 파일이 없습니다: {quarantine}")
        actual_size = quarantine.stat().st_size
        if actual_size != int(row["size_bytes"]):
            raise RuntimeError(f"격리 파일 크기 불일치: {quarantine}")
        total += actual_size
        if index % 20_000 == 0:
            print(f"격리 재검증 {index:,}/{len(rows):,}")
    if total != EXPECTED_TARGET["snapshotBytes"]:
        raise RuntimeError(f"격리 총 바이트 불일치: {total}")
    print(
        f"격리 재검증 완료: {len(rows):,}개 / "
        f"{total / 1024**3:.3f}GB"
    )


def verify_source_restored(rows: list[dict[str, object]]) -> None:
    total = 0
    for index, row in enumerate(rows, start=1):
        source = Path(str(row["source_path"]))
        quarantine = Path(str(row["quarantine_path"]))
        if quarantine.exists():
            raise RuntimeError(f"격리 위치에 파일이 남아 있습니다: {quarantine}")
        if not source.is_file():
            raise RuntimeError(f"복원된 원본 파일이 없습니다: {source}")
        actual_size = source.stat().st_size
        if actual_size != int(row["size_bytes"]):
            raise RuntimeError(f"복원 파일 크기 불일치: {source}")
        total += actual_size
        if index % 20_000 == 0:
            print(f"복원 재검증 {index:,}/{len(rows):,}")
    if total != EXPECTED_TARGET["snapshotBytes"]:
        raise RuntimeError(f"복원 총 바이트 불일치: {total}")
    print(
        f"파일 복원 검증 완료: {len(rows):,}개 / "
        f"{total / 1024**3:.3f}GB"
    )


def verify_backups(operation: Path) -> dict[str, str]:
    backup = operation / "backup"
    names = (
        "visionflow-full.sql",
        "target-ai-inference-event.sql",
        "target-ai-detection.sql",
        "target-ai-alert.sql",
    )
    checksums: dict[str, str] = {}
    for name in names:
        path = backup / name
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"DB 백업 파일이 없거나 비어 있습니다: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        checksums[name] = digest.hexdigest()
        print(
            f"백업 검증: {name} / "
            f"{path.stat().st_size / 1024**2:.2f}MB"
        )

    checksum_path = backup / "backup-checksums.sha256"
    checksum_path.write_text(
        "".join(f"{digest}  {name}\n" for name, digest in checksums.items()),
        encoding="ascii",
    )
    return checksums


def is_running(container: str) -> bool:
    completed = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", container],
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    return completed.returncode == 0 and completed.stdout.strip() == "true"


def stop_services() -> list[str]:
    running = [name for name in SERVICE_CONTAINERS if is_running(name)]
    for name in running:
        print(f"컨테이너 중지: {name}")
        run(["docker", "stop", name])
    return running


def start_services(containers: list[str]) -> None:
    for name in reversed(containers):
        print(f"컨테이너 시작: {name}")
        completed = subprocess.run(
            ["docker", "start", name],
            text=True,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            print(
                f"경고: {name} 재시작 실패: {completed.stderr}",
                file=sys.stderr,
            )


def wait_health(container: str, timeout_seconds: int = 180) -> str:
    deadline = time.time() + timeout_seconds
    last = "unknown"
    while time.time() < deadline:
        completed = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
                container,
            ],
            text=True,
            capture_output=True,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode == 0:
            last = completed.stdout.strip()
            if last in {"healthy", "running"}:
                return last
            if last == "unhealthy":
                return last
        time.sleep(2)
    return last


def move_back(rows: list[dict[str, object]]) -> None:
    moved = 0
    for index, row in enumerate(rows, start=1):
        source = Path(str(row["source_path"]))
        quarantine = Path(str(row["quarantine_path"]))

        if source.exists() and quarantine.exists():
            raise RuntimeError(
                f"원본과 격리 파일이 동시에 존재합니다: {source.name}"
            )
        if quarantine.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            os.replace(quarantine, source)
            moved += 1
        elif not source.exists():
            raise RuntimeError(
                f"원본과 격리 위치 모두 파일이 없습니다: {source.name}"
            )

        if index % 20_000 == 0:
            print(f"파일 복원 {index:,}/{len(rows):,}")
    print(f"파일 이동 복원 완료: {moved:,}개")


def execute_delete() -> int:
    sql = (
        "START TRANSACTION; "
        f"DELETE FROM ai_inference_event WHERE {condition()}; "
        "SELECT ROW_COUNT(); "
        "COMMIT;"
    )
    output = mysql_query(sql).strip()
    if not output:
        raise RuntimeError("DELETE 결과가 비어 있습니다.")
    return int(output.splitlines()[-1].strip())


def run_audit(root: Path) -> int | None:
    audit = root / "scripts" / "run-visionflow-storage-audit.bat"
    if not audit.is_file():
        return None
    print("\n저장소 감사 실행...")
    completed = subprocess.run(
        ["cmd", "/d", "/c", str(audit)],
        cwd=str(root),
        text=True,
        check=False,
    )
    return completed.returncode


def delete_command(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    operation = Path(args.operation).resolve()
    metadata = load_operation(operation)

    if metadata.get("status") != "QUARANTINED":
        raise RuntimeError(
            f"삭제 가능 상태가 아닙니다: {metadata.get('status')}"
        )
    if not args.apply or args.confirm != DELETE_TOKEN:
        raise RuntimeError(
            f"--apply --confirm {DELETE_TOKEN}가 필요합니다."
        )

    rows = load_manifest(operation)
    verify_quarantine(rows)
    checksums = verify_backups(operation)
    require_equal(target_counts(), EXPECTED_TARGET, "삭제 전 대상 집계")

    running = stop_services()
    try:
        metadata["status"] = "DB_DELETE_IN_PROGRESS"
        metadata["backupChecksums"] = checksums
        save_operation(operation, metadata)

        # Services are stopped, so the approved target cannot change.
        require_equal(target_counts(), EXPECTED_TARGET, "중지 후 대상 집계")
        deleted = execute_delete()
        if deleted != EXPECTED_TARGET["events"]:
            raise RuntimeError(
                f"삭제된 이벤트 수 불일치: {deleted} "
                f"!= {EXPECTED_TARGET['events']}"
            )

        require_equal(
            target_counts(),
            {
                "events": 0,
                "detections": 0,
                "alerts": 0,
                "snapshots": 0,
                "snapshotBytes": 0,
            },
            "삭제 후 대상 잔여 집계",
        )
        require_equal(total_counts(), EXPECTED_REMAINING, "삭제 후 전체 집계")

        metadata["status"] = "DB_DELETED"
        metadata["dbDeletedAt"] = now_utc()
        metadata["deletedEvents"] = deleted
        metadata["remaining"] = EXPECTED_REMAINING
        save_operation(operation, metadata)
    finally:
        start_services(running)

    for name in reversed(running):
        print(f"{name} 상태: {wait_health(name)}")

    audit_code = run_audit(root)
    metadata = load_operation(operation)
    metadata["auditExitCodeAfterDelete"] = audit_code
    save_operation(operation, metadata)

    print("\nDB 정리 완료")
    print(json.dumps(EXPECTED_REMAINING, ensure_ascii=False, indent=2))
    print(f"격리 파일은 보존 중입니다: {operation / 'quarantine'}")
    return 0


def restore_command(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    operation = Path(args.operation).resolve()
    metadata = load_operation(operation)

    if metadata.get("status") not in {"DB_DELETED", "QUARANTINED"}:
        raise RuntimeError(
            f"복원 가능 상태가 아닙니다: {metadata.get('status')}"
        )
    if not args.apply or args.confirm != RESTORE_TOKEN:
        raise RuntimeError(
            f"--apply --confirm {RESTORE_TOKEN}가 필요합니다."
        )

    rows = load_manifest(operation)
    verify_backups(operation)

    running = stop_services()
    try:
        current_target = target_counts()
        if current_target["events"] == 0:
            backup = operation / "backup"
            print("대상 이벤트 DB 복원...")
            mysql_import(backup / "target-ai-inference-event.sql")
            print("대상 Detection DB 복원...")
            mysql_import(backup / "target-ai-detection.sql")
            print("대상 Alert DB 복원...")
            mysql_import(backup / "target-ai-alert.sql")
        elif current_target != EXPECTED_TARGET:
            raise RuntimeError(
                "부분적인 대상 DB 데이터가 존재하여 자동 복원을 중단합니다.\n"
                f"{json.dumps(current_target, ensure_ascii=False)}"
            )

        require_equal(target_counts(), EXPECTED_TARGET, "DB 복원 후 대상 집계")
        move_back(rows)
        verify_source_restored(rows)

        metadata["status"] = "RESTORED"
        metadata["restoredAt"] = now_utc()
        save_operation(operation, metadata)
    finally:
        start_services(running)

    for name in reversed(running):
        print(f"{name} 상태: {wait_health(name)}")

    audit_code = run_audit(root)
    metadata = load_operation(operation)
    metadata["auditExitCodeAfterRestore"] = audit_code
    save_operation(operation, metadata)

    print("\nDB와 스냅샷 복원 완료")
    return 0


def status_command(args: argparse.Namespace) -> int:
    operation = Path(args.operation).resolve()
    print(
        json.dumps(
            load_operation(operation),
            ensure_ascii=False,
            indent=2,
        )
    )
    print("\n현재 대상 집계:")
    print(json.dumps(target_counts(), ensure_ascii=False, indent=2))
    print("\n현재 전체 집계:")
    print(json.dumps(total_counts(), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VisionFlow AI 격리 후 DB 삭제 및 복원"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    delete = sub.add_parser("delete")
    delete.add_argument("--root", default=ROOT_DEFAULT)
    delete.add_argument("--operation", required=True)
    delete.add_argument("--apply", action="store_true")
    delete.add_argument("--confirm")
    delete.set_defaults(func=delete_command)

    restore = sub.add_parser("restore")
    restore.add_argument("--root", default=ROOT_DEFAULT)
    restore.add_argument("--operation", required=True)
    restore.add_argument("--apply", action="store_true")
    restore.add_argument("--confirm")
    restore.set_defaults(func=restore_command)

    status = sub.add_parser("status")
    status.add_argument("--operation", required=True)
    status.set_defaults(func=status_command)
    return parser


def main() -> int:
    if shutil.which("docker") is None:
        raise RuntimeError("docker 명령을 찾을 수 없습니다.")
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n사용자 중단", file=sys.stderr)
        raise SystemExit(130)
    except Exception as error:
        print(f"\n오류: {error}", file=sys.stderr)
        raise SystemExit(1)
