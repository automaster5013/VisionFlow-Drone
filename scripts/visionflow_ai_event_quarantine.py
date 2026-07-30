#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DEFAULT = r"C:\VisionFlow-Drone"
MYSQL_CONTAINER = "visionflow-mysql"
SOURCE_ID = "browser-camera-001"
SESSION_IDS = (
    "720f652c-8498-4686-a20d-fb573b7ef562",
    "890614dc-71ff-45ea-bf9a-62177cde072f",
    "a8edd33f-7e44-4e01-93b7-2bdaafff5587",
)
MIN_EVENT_ID = 6943
MAX_EVENT_ID = 140249
EXPECTED_EVENTS = 133_307
EXPECTED_DETECTIONS = 333_658
EXPECTED_ALERTS = 133_307
EXPECTED_SNAPSHOTS = 133_306
EXPECTED_BYTES = 15_413_065_831
CONFIRM_TOKEN = "QUARANTINE_133306_SNAPSHOTS"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def condition(alias: str = "") -> str:
    p = f"{alias}." if alias else ""
    sessions = ",".join(f"'{s}'" for s in SESSION_IDS)
    return (
        f"{p}source_id='{SOURCE_ID}' AND "
        f"{p}session_id IN ({sessions}) AND "
        f"{p}id BETWEEN {MIN_EVENT_ID} AND {MAX_EVENT_ID}"
    )


def run(args: list[str], *, text: bool = True, stdout=None):
    completed = subprocess.run(
        args,
        text=text,
        stdout=stdout if stdout is not None else subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8" if text else None,
        errors="replace" if text else None,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr if text else completed.stderr.decode("utf-8", "replace")
        raise RuntimeError(f"명령 실패: {' '.join(args)}\n{stderr}")
    return completed


def mysql_query(sql: str) -> str:
    cmd = (
        'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -D "$MYSQL_DATABASE" '
        '--batch --raw --skip-column-names '
        f'-e {shlex.quote(sql)}'
    )
    return run(["docker", "exec", MYSQL_CONTAINER, "sh", "-lc", cmd]).stdout


def dump_to(path: Path, table: str | None = None, where: str | None = None) -> None:
    opts = [
        "mysqldump",
        '-uroot',
        '-p"$MYSQL_ROOT_PASSWORD"',
        "--single-transaction",
        "--quick",
        "--hex-blob",
    ]
    if table is None:
        opts += ["--routines", "--triggers", "--events", '"$MYSQL_DATABASE"']
    else:
        opts += [
            "--no-create-info",
            "--skip-triggers",
            "--complete-insert",
            '"$MYSQL_DATABASE"',
            table,
        ]
        if where:
            opts.append(f"--where={shlex.quote(where)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        run(["docker", "exec", MYSQL_CONTAINER, "sh", "-lc", " ".join(opts)], text=False, stdout=f)
    if path.stat().st_size == 0:
        raise RuntimeError(f"DB 백업 파일이 비어 있습니다: {path}")


def target_counts() -> dict[str, int]:
    sql = (
        "SELECT "
        f"(SELECT COUNT(*) FROM ai_inference_event WHERE {condition()}),"
        "(SELECT COUNT(*) FROM ai_detection d JOIN ai_inference_event e ON e.id=d.event_id "
        f"WHERE {condition('e')}),"
        "(SELECT COUNT(*) FROM ai_alert a JOIN ai_inference_event e ON e.id=a.event_id "
        f"WHERE {condition('e')}),"
        f"(SELECT COUNT(*) FROM ai_inference_event WHERE {condition()} AND snapshot_file_name IS NOT NULL),"
        f"(SELECT COALESCE(SUM(snapshot_size_bytes),0) FROM ai_inference_event WHERE {condition()} AND snapshot_file_name IS NOT NULL);"
    )
    values = mysql_query(sql).strip().split("\t")
    if len(values) != 5:
        raise RuntimeError(f"대상 집계 결과 형식 오류: {values}")
    return {
        "events": int(values[0]),
        "detections": int(values[1]),
        "alerts": int(values[2]),
        "snapshots": int(values[3]),
        "snapshotBytes": int(values[4]),
    }


def assert_counts(counts: dict[str, int]) -> None:
    expected = {
        "events": EXPECTED_EVENTS,
        "detections": EXPECTED_DETECTIONS,
        "alerts": EXPECTED_ALERTS,
        "snapshots": EXPECTED_SNAPSHOTS,
        "snapshotBytes": EXPECTED_BYTES,
    }
    if counts != expected:
        raise RuntimeError(
            "승인된 대상 집계와 다릅니다.\n"
            f"예상={json.dumps(expected, ensure_ascii=False)}\n"
            f"실제={json.dumps(counts, ensure_ascii=False)}"
        )


def read_snapshot_rows(root: Path, operation: Path) -> list[dict[str, object]]:
    sql = (
        "SELECT id,session_id,snapshot_file_name,snapshot_size_bytes "
        f"FROM ai_inference_event WHERE {condition()} "
        "AND snapshot_file_name IS NOT NULL ORDER BY id;"
    )
    source_dir = root / "artifacts" / "backend-data" / "ai-snapshots"
    quarantine_dir = operation / "quarantine" / "files"
    rows: list[dict[str, object]] = []
    for line in mysql_query(sql).splitlines():
        if not line.strip():
            continue
        event_id_s, session_id, file_name, size_s = line.split("\t")
        event_id = int(event_id_s)
        size = int(size_s)
        if file_name != f"event-{event_id}.jpg" or Path(file_name).name != file_name:
            raise RuntimeError(f"스냅샷 파일명 검증 실패: {event_id} / {file_name}")
        bucket_start = (event_id // 10_000) * 10_000
        bucket = f"{bucket_start:06d}-{bucket_start + 9999:06d}"
        rows.append({
            "event_id": event_id,
            "session_id": session_id,
            "file_name": file_name,
            "size_bytes": size,
            "source_path": str(source_dir / file_name),
            "quarantine_path": str(quarantine_dir / bucket / file_name),
        })
    if len(rows) != EXPECTED_SNAPSHOTS:
        raise RuntimeError(f"manifest 건수 불일치: {len(rows)}")
    if sum(int(r["size_bytes"]) for r in rows) != EXPECTED_BYTES:
        raise RuntimeError("manifest 총 바이트 불일치")
    return rows


def write_manifest(operation: Path, rows: list[dict[str, object]]) -> Path:
    path = operation / "manifest" / "target-snapshots.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def verify_sources(rows: list[dict[str, object]]) -> None:
    total = 0
    for i, row in enumerate(rows, 1):
        path = Path(str(row["source_path"]))
        if not path.is_file():
            raise RuntimeError(f"원본 파일 없음: {path}")
        size = path.stat().st_size
        if size != int(row["size_bytes"]):
            raise RuntimeError(f"원본 크기 불일치: {path}")
        total += size
        if i % 10_000 == 0:
            print(f"원본 검증 {i:,}/{len(rows):,}")
    if total != EXPECTED_BYTES:
        raise RuntimeError(f"원본 총 바이트 불일치: {total}")
    print(f"원본 검증 완료: {len(rows):,}개 / {total / 1024**3:.3f}GB")


def move_files(operation: Path, rows: list[dict[str, object]]) -> None:
    moved: list[dict[str, object]] = []
    try:
        for i, row in enumerate(rows, 1):
            src = Path(str(row["source_path"]))
            dst = Path(str(row["quarantine_path"]))
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dst)
            moved.append(row)
            if i % 1_000 == 0 or i == len(rows):
                (operation / "move-progress.json").write_text(
                    json.dumps({"moved": i, "total": len(rows), "updatedAt": now_utc()}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            if i % 10_000 == 0:
                print(f"격리 이동 {i:,}/{len(rows):,}")
    except BaseException:
        print("격리 실패: 이동된 파일을 자동 복원합니다.", file=sys.stderr)
        for row in reversed(moved):
            src = Path(str(row["source_path"]))
            dst = Path(str(row["quarantine_path"]))
            if dst.exists() and not src.exists():
                src.parent.mkdir(parents=True, exist_ok=True)
                os.replace(dst, src)
        raise


def verify_quarantine(rows: list[dict[str, object]]) -> None:
    total = 0
    for i, row in enumerate(rows, 1):
        src = Path(str(row["source_path"]))
        dst = Path(str(row["quarantine_path"]))
        if src.exists():
            raise RuntimeError(f"원본 위치에 파일이 남음: {src}")
        if not dst.is_file() or dst.stat().st_size != int(row["size_bytes"]):
            raise RuntimeError(f"격리 파일 검증 실패: {dst}")
        total += dst.stat().st_size
        if i % 10_000 == 0:
            print(f"격리 검증 {i:,}/{len(rows):,}")
    if total != EXPECTED_BYTES:
        raise RuntimeError(f"격리 총 바이트 불일치: {total}")
    print(f"격리 검증 완료: {len(rows):,}개 / {total / 1024**3:.3f}GB")


def main() -> int:
    parser = argparse.ArgumentParser(description="VisionFlow AI 폭증 스냅샷 백업 및 격리")
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    args = parser.parse_args()

    if shutil.which("docker") is None:
        raise RuntimeError("docker 명령을 찾을 수 없습니다.")

    root = Path(args.root).resolve()
    counts = target_counts()
    assert_counts(counts)
    print(json.dumps(counts, ensure_ascii=False, indent=2))

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    operation = root / "artifacts" / "ai-event-cleanup" / f"cleanup-{stamp}"
    operation.mkdir(parents=True, exist_ok=False)
    metadata = {
        "status": "CREATED",
        "createdAt": now_utc(),
        "root": str(root),
        "sourceId": SOURCE_ID,
        "sessionIds": list(SESSION_IDS),
        "minEventId": MIN_EVENT_ID,
        "maxEventId": MAX_EVENT_ID,
        "expected": counts,
    }
    op_file = operation / "operation.json"
    op_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = read_snapshot_rows(root, operation)
    manifest = write_manifest(operation, rows)
    verify_sources(rows)

    if not args.apply:
        metadata["status"] = "DRY_RUN_COMPLETE"
        metadata["manifest"] = str(manifest)
        op_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\nDRY-RUN 완료: DB와 파일은 변경되지 않았습니다.")
        print(f"작업 디렉터리: {operation}")
        return 0

    if args.confirm != CONFIRM_TOKEN:
        raise RuntimeError(f"--confirm {CONFIRM_TOKEN}가 필요합니다.")

    metadata["status"] = "BACKUP_IN_PROGRESS"
    op_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    backup = operation / "backup"
    print("전체 DB 백업 생성 중...")
    dump_to(backup / "visionflow-full.sql")
    print("대상 이벤트 백업 생성 중...")
    dump_to(backup / "target-ai-inference-event.sql", "ai_inference_event", condition())
    print("대상 Detection 백업 생성 중...")
    dump_to(backup / "target-ai-detection.sql", "ai_detection", f"event_id BETWEEN {MIN_EVENT_ID} AND {MAX_EVENT_ID}")
    print("대상 Alert 백업 생성 중...")
    dump_to(backup / "target-ai-alert.sql", "ai_alert", f"event_id BETWEEN {MIN_EVENT_ID} AND {MAX_EVENT_ID}")
    for p in sorted(backup.glob("*.sql")):
        print(f"백업 완료: {p.name} / {p.stat().st_size / 1024**2:.2f}MB")

    metadata["status"] = "BACKUP_COMPLETE"
    metadata["manifest"] = str(manifest)
    op_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    move_files(operation, rows)
    verify_quarantine(rows)
    metadata["status"] = "QUARANTINED"
    metadata["quarantinedAt"] = now_utc()
    op_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n격리 완료. DB 레코드는 아직 삭제하지 않았습니다.")
    print(f"작업 디렉터리: {operation}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n사용자 중단", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"\n오류: {exc}", file=sys.stderr)
        raise SystemExit(1)
