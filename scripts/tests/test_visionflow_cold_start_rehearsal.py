from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from scripts.visionflow_cold_start_rehearsal import (
    REQUIRED_MARKERS,
    RehearsalError,
    resolve_handoff,
    run_rehearsal,
    sha256_file,
)


NOW = datetime(2026, 7, 22, 7, 0, tzinfo=timezone.utc)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def marker_files() -> dict[str, bytes]:
    files = {
        alternatives[0]: f"marker:{key}".encode()
        for key, alternatives in REQUIRED_MARKERS.items()
    }
    files[".env.docker.example"] = b"VISIONFLOW_ENV=example"
    files["01_frontend/visionflow-web/public/logo.png"] = b"small-static-ui-image"
    return files


def create_source(files: dict[str, bytes], *, symlink: str | None = None) -> tuple[bytes, str]:
    entries = [
        {"path": path, "sizeBytes": len(value), "sha256": sha(value)}
        for path, value in sorted(files.items())
    ]
    manifest = {
        "schemaVersion": 1,
        "project": "visionflow",
        "operation": "PORTABLE_SOURCE_RELEASE",
        "summary": {
            "includedFiles": len(entries),
            "includedBytes": sum(len(value) for value in files.values()),
        },
        "files": entries,
        "excluded": [],
        "safety": {},
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("VisionFlow-Drone/README-MIGRATION.md", "migration")
        archive.writestr("VisionFlow-Drone/SOURCE_MANIFEST.json", manifest_bytes)
        for path, value in files.items():
            archive_path = f"VisionFlow-Drone/{path}"
            if path == symlink:
                info = zipfile.ZipInfo(archive_path)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, value)
            else:
                archive.writestr(archive_path, value)
    return buffer.getvalue(), sha(manifest_bytes)


def create_handoff(
    path: Path,
    *,
    files: dict[str, bytes] | None = None,
    manifest_sha_override: str | None = None,
    symlink: str | None = None,
) -> None:
    source, manifest_sha = create_source(files or marker_files(), symlink=symlink)
    source_path = "VisionFlow-Handoff/source/visionflow-source-release-test.zip"
    readme_path = "VisionFlow-Handoff/README.md"
    readme = b"handoff"
    manifest = {
        "schemaVersion": 1,
        "project": "visionflow",
        "operation": "MIGRATION_HANDOFF",
        "source": {
            "archivePath": source_path,
            "sha256": sha(source),
            "manifestSha256": manifest_sha_override or manifest_sha,
            "fileCount": len(files or marker_files()),
        },
        "files": [
            {"archivePath": source_path, "sizeBytes": len(source), "sha256": sha(source)},
            {"archivePath": readme_path, "sizeBytes": len(readme), "sha256": sha(readme)},
        ],
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(source_path, source)
        archive.writestr(readme_path, readme)
        archive.writestr(
            "VisionFlow-Handoff/HANDOFF_MANIFEST.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
    path.with_suffix(".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="utf-8"
    )


class ColdStartRehearsalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.handoff_root = self.root / "artifacts/migration-handoff"
        self.output = self.root / "artifacts/cold-start-rehearsal"
        self.handoff_root.mkdir(parents=True)
        self.output.mkdir(parents=True)
        self.handoff = self.handoff_root / "visionflow-migration-handoff-20260722T060000Z.zip"
        create_handoff(self.handoff)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_case(self, *, keep: bool = False):
        return run_rehearsal(
            self.root,
            self.handoff,
            output_root=self.output,
            keep_workspace=keep,
            now=NOW,
        )

    def test_success_creates_ready_reports_and_preserves_original(self) -> None:
        before = sha256_file(self.handoff)
        json_path, html_path, sidecar, report, exit_code = self.run_case()
        self.assertEqual(0, exit_code)
        self.assertEqual("COLD_START_READY_WITH_DEFERRED", report["status"])
        self.assertTrue(json_path.is_file())
        self.assertTrue(html_path.is_file())
        self.assertTrue(sidecar.is_file())
        self.assertEqual(before, sha256_file(self.handoff))
        self.assertEqual(0, report["summary"]["blocking"])

    def test_default_workspace_is_removed(self) -> None:
        _, _, _, report, _ = self.run_case()
        self.assertFalse(report["workspace"]["retained"])
        self.assertFalse(any(self.output.glob(".rehearsal-*")))
        self.assertFalse(any(self.output.glob("workspace-*")))

    def test_keep_workspace_retains_verified_source(self) -> None:
        _, _, _, report, exit_code = self.run_case(keep=True)
        self.assertEqual(0, exit_code)
        retained = self.root / report["workspace"]["path"]
        self.assertTrue((retained / "compose.yaml").is_file())
        self.assertTrue((retained / "SOURCE_MANIFEST.json").is_file())

    def test_missing_required_marker_blocks_report(self) -> None:
        files = marker_files()
        files.pop("01_frontend/visionflow-web/package-lock.json")
        create_handoff(self.handoff, files=files)
        _, _, _, report, exit_code = self.run_case()
        self.assertEqual(1, exit_code)
        self.assertEqual("BLOCKED", report["status"])
        missing = [item for item in report["markers"] if item["status"] == "MISSING"]
        self.assertEqual(["frontend-lock"], [item["key"] for item in missing])

    def test_tampered_handoff_sidecar_is_rejected(self) -> None:
        self.handoff.with_suffix(".sha256").write_text(
            f"{'0' * 64}  {self.handoff.name}\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(RehearsalError, "sidecar와 다릅니다"):
            self.run_case()

    def test_handoff_source_manifest_identity_mismatch_is_rejected(self) -> None:
        create_handoff(self.handoff, manifest_sha_override="f" * 64)
        with self.assertRaisesRegex(RehearsalError, "manifest SHA-256"):
            self.run_case()

    def test_model_weight_in_source_is_rejected(self) -> None:
        files = marker_files()
        files["03_ai-server/visionflow-ai/models/best.pt"] = b"model"
        create_handoff(self.handoff, files=files)
        with self.assertRaisesRegex(RehearsalError, "런타임 또는 대용량"):
            self.run_case()

    def test_source_symlink_is_rejected(self) -> None:
        target = "scripts/run-visionflow-acceptance.bat"
        create_handoff(self.handoff, symlink=target)
        with self.assertRaisesRegex(RehearsalError, "심볼릭 링크"):
            self.run_case()

    def test_output_outside_artifacts_is_rejected(self) -> None:
        with self.assertRaisesRegex(RehearsalError, "출력 폴더"):
            run_rehearsal(
                self.root,
                self.handoff,
                output_root=self.root / "outside",
                keep_workspace=False,
                now=NOW,
            )

    def test_newest_invalid_handoff_does_not_fall_back(self) -> None:
        invalid = self.handoff_root / "visionflow-migration-handoff-20260722T070000Z.zip"
        invalid.write_bytes(b"invalid")
        invalid.with_suffix(".sha256").write_text(
            f"{sha256_file(invalid)}  {invalid.name}\n", encoding="utf-8"
        )
        newer = self.handoff.stat().st_mtime_ns + 2_000_000_000
        os.utime(invalid, ns=(newer, newer))
        selected = resolve_handoff(self.root, None)
        self.assertEqual(invalid, selected)
        with self.assertRaisesRegex(RehearsalError, "손상"):
            run_rehearsal(
                self.root,
                selected,
                output_root=self.output,
                keep_workspace=False,
                now=NOW,
            )


if __name__ == "__main__":
    unittest.main()
