#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT_DEFAULT = r"C:\VisionFlow-Drone"
MARKER = "VISIONFLOW_PRESENTATION_DEMO_MODE_LINK"


def read_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    return raw.decode("utf-8-sig"), "\r\n" if b"\r\n" in raw else "\n"


def write_text(path: Path, text: str, newline: str = "\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    path.write_bytes(normalized.replace("\n", newline).encode("utf-8"))


def relative(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest().upper()


def sidebar_score(path: Path, text: str) -> int:
    lower_name = path.name.lower()
    lower_path = str(path).lower()
    if "node_modules" in lower_path or ".next" in lower_path:
        return -1000

    score = 0
    if "sidebar" in lower_name:
        score += 140
    if "navigation" in lower_name or "side-nav" in lower_name:
        score += 100
    if "nav" in lower_name:
        score += 60
    if "layout" in lower_name:
        score += 30
    if "<nav" in text and "</nav>" in text:
        score += 100
    if "<aside" in text and "</aside>" in text:
        score += 40
    if 'href="/drones"' in text or "href={'/drones'}" in text:
        score += 100
    if "/dashboard" in text:
        score += 20
    if "드론" in text:
        score += 20
    return score


def locate_sidebar(frontend: Path, explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = frontend / path
        if not path.is_file():
            raise RuntimeError(f"지정한 사이드바 파일이 없습니다: {path}")
        return path

    candidates: list[tuple[int, Path]] = []
    for path in (frontend / "src").rglob("*.tsx"):
        try:
            text, _ = read_text(path)
        except (UnicodeDecodeError, OSError):
            continue
        score = sidebar_score(path, text)
        if score > 0:
            candidates.append((score, path))

    if not candidates:
        raise RuntimeError(
            "사이드바 후보를 찾지 못했습니다. "
            "--sidebar-file 옵션으로 파일을 지정해 주세요."
        )

    candidates.sort(key=lambda item: (-item[0], len(str(item[1]))))
    score, selected = candidates[0]
    if score < 120:
        details = "\n".join(
            f"  score={value}: {path}"
            for value, path in candidates[:10]
        )
        raise RuntimeError(
            "사이드바 파일을 안전하게 확정하지 못했습니다.\n" + details
        )
    return selected


def ensure_link_import(text: str, newline: str) -> str:
    if re.search(r'from\s+["\']next/link["\']', text):
        return text

    statement = f'import Link from "next/link";{newline}'
    directive = re.match(r'^["\']use client["\'];\s*', text)
    if directive:
        end = directive.end()
        return text[:end] + newline + statement + text[end:]

    first_import = re.search(r"^import\s", text, re.MULTILINE)
    if first_import:
        index = first_import.start()
        return text[:index] + statement + text[index:]

    return statement + newline + text


def patch_sidebar(path: Path) -> str:
    text, newline = read_text(path)
    if MARKER in text:
        return "ALREADY_PATCHED"

    text = ensure_link_import(text, newline)
    link = (
        f'{newline}      {{/* {MARKER} */}}{newline}'
        f'      <Link{newline}'
        f'        href="/demo-mode"{newline}'
        f'        className="mt-2 flex items-center gap-3 rounded-xl border '
        f'border-violet-400/40 bg-violet-500/10 px-4 py-3 font-semibold '
        f'text-violet-700 transition hover:bg-violet-500/20 dark:text-violet-200"{newline}'
        f'      >{newline}'
        f'        <span aria-hidden="true">🎬</span>{newline}'
        f'        <span>시연 모드</span>{newline}'
        f'      </Link>{newline}'
    )

    if "</nav>" in text:
        index = text.rfind("</nav>")
    elif "</aside>" in text:
        index = text.rfind("</aside>")
    else:
        raise RuntimeError(
            f"삽입 위치 </nav> 또는 </aside>가 없습니다: {path}"
        )

    text = text[:index] + link + text[index:]
    write_text(path, text, newline)
    return "PATCHED"


def detect_frontend_service(compose_path: Path) -> str:
    text, _ = read_text(compose_path)
    lines = text.splitlines()

    for index, line in enumerate(lines):
        if re.match(r"^\s{4}container_name:\s*visionflow-frontend\s*$", line):
            for previous in range(index - 1, -1, -1):
                match = re.match(
                    r"^\s{2}([A-Za-z0-9_.-]+):\s*$",
                    lines[previous],
                )
                if match:
                    return match.group(1)

    for candidate in ("frontend", "frontend-web", "web"):
        if re.search(
            rf"^\s{{2}}{re.escape(candidate)}:\s*$",
            text,
            re.MULTILINE,
        ):
            return candidate

    raise RuntimeError(
        "compose.yaml에서 visionflow-frontend 서비스 키를 찾지 못했습니다."
    )


def detect_workdir(frontend: Path) -> str:
    for dockerfile in (
        frontend / "Dockerfile",
        frontend / "docker" / "Dockerfile",
    ):
        if not dockerfile.is_file():
            continue
        text, _ = read_text(dockerfile)
        values = re.findall(
            r"^\s*WORKDIR\s+(\S+)",
            text,
            re.MULTILINE,
        )
        if values:
            return values[-1].rstrip("/")
    return "/app"


def video_rank(path: Path) -> tuple[int, int]:
    name = path.name.lower()
    score = 0
    if name == "sample.mp4":
        score += 100
    if any(word in name for word in ("hardhat", "helmet", "ppe")):
        score += 80
    if any(word in name for word in ("dummy", "demo", "test")):
        score += 40
    return score, path.stat().st_size


def select_video(root: Path, explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = root / path
        if not path.is_file():
            raise RuntimeError(f"지정한 더미영상이 없습니다: {path}")
        return path.resolve()

    known = (
        root / "artifacts" / "backend-data" / "dummy" / "sample.mp4",
        root / "03_ai-server" / "visionflow-ai" / "data" / "dummy" / "sample.mp4",
        root / "artifacts" / "ai-output" / "sample.mp4",
    )
    for path in known:
        if path.is_file():
            return path.resolve()

    candidates: list[Path] = []
    ignored = {
        "node_modules",
        ".next",
        ".git",
        "patch-backups",
        "ai-event-cleanup",
        "presentation-demo",
    }
    for path in root.rglob("*.mp4"):
        if any(part in ignored for part in path.parts):
            continue
        if path.is_file() and path.stat().st_size > 100_000:
            candidates.append(path)

    if not candidates:
        raise RuntimeError(
            "발표용 MP4를 찾지 못했습니다. "
            "--dummy-video 옵션으로 지정해 주세요."
        )

    candidates.sort(key=video_rank, reverse=True)
    return candidates[0].resolve()


def link_or_copy(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    try:
        os.link(source, target)
        return "HARDLINK"
    except OSError:
        shutil.copy2(source, target)
        return "COPY"


def compose_override(service: str, workdir: str) -> str:
    return (
        "services:\n"
        f"  {service}:\n"
        "    volumes:\n"
        "      - type: bind\n"
        "        source: ./artifacts/presentation-demo\n"
        f"        target: {workdir}/public/demo\n"
        "        read_only: true\n"
    )


def existing_compose_files(root: Path) -> list[str]:
    names = (
        "compose.yaml",
        "compose.gpu.yaml",
        "compose.model.yaml",
        "compose.mobile-https.yaml",
        "compose.presentation.yaml",
    )
    return [name for name in names if (root / name).is_file()]


def deployment_bat(root: Path, service: str) -> bytes:
    args = " ".join(
        f'-f "{name}"' for name in existing_compose_files(root)
    )
    mobile = (
        " mobile-https"
        if (root / "compose.mobile-https.yaml").is_file()
        else ""
    )
    content = (
        "@echo off\r\n"
        "setlocal EnableExtensions\r\n"
        'cd /d "C:\\VisionFlow-Drone"\r\n'
        f"docker compose {args} config >nul\r\n"
        "if errorlevel 1 (\r\n"
        "  echo ERROR: Docker Compose validation failed.\r\n"
        "  exit /b 2\r\n"
        ")\r\n"
        f"docker compose {args} up -d --build {service}{mobile}\r\n"
        "if errorlevel 1 exit /b 2\r\n"
        "echo.\r\n"
        "echo Presentation demo mode deployment: COMPLETE\r\n"
        "docker ps --format \"table {{.Names}}\\t{{.Status}}\\t{{.Ports}}\"\r\n"
        "echo.\r\n"
        "echo Open:\r\n"
        "echo   http://localhost:3000/demo-mode\r\n"
        "if exist \"artifacts\\mobile-https\\phone\\visionflow-mobile-connection.json\" (\r\n"
        "  powershell -NoProfile -Command \"$j=Get-Content -LiteralPath 'artifacts\\mobile-https\\phone\\visionflow-mobile-connection.json' -Raw -Encoding UTF8|ConvertFrom-Json;Write-Host ('  '+$j.url+'demo-mode')\"\r\n"
        ")\r\n"
        "exit /b 0\r\n"
    )
    return content.encode("ascii")


def backup_targets(
    root: Path,
    backup: Path,
    targets: list[Path],
) -> dict[str, bool]:
    existence: dict[str, bool] = {}
    for target in targets:
        rel = relative(root, target)
        existence[rel] = target.is_file()
        if target.is_file():
            saved = backup / "files" / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
    return existence


def restore(root: Path, backup: Path) -> None:
    manifest_path = backup / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"manifest.json이 없습니다: {manifest_path}")

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8-sig")
    )
    existence: dict[str, bool] = manifest["targetExistence"]

    for rel, existed in existence.items():
        target = root / Path(rel)
        saved = backup / "files" / Path(rel)
        if existed:
            if not saved.is_file():
                raise RuntimeError(f"백업 파일이 없습니다: {saved}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(saved, target)
        elif target.exists() and (target.is_file() or target.is_symlink()):
            target.unlink()

    print(f"롤백 완료: {backup}")


def latest_backup(root: Path) -> Path:
    base = root / "artifacts" / "patch-backups"
    values = sorted(
        (
            path
            for path in base.glob("presentation-demo-*")
            if path.is_dir()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not values:
        raise RuntimeError("presentation-demo 백업이 없습니다.")
    return values[0]


def apply(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    frontend = root / "01_frontend" / "visionflow-web"
    compose_path = root / "compose.yaml"

    for required in (
        frontend / "src" / "app",
        frontend / "src" / "components",
        compose_path,
    ):
        if not required.exists():
            raise RuntimeError(f"필수 경로가 없습니다: {required}")

    script_dir = Path(__file__).resolve().parent
    template_dir = script_dir.parent / "templates"
    component_template = template_dir / "demo-mode-console.tsx"
    page_template = template_dir / "demo-mode-page.tsx"
    if not component_template.is_file() or not page_template.is_file():
        raise RuntimeError(f"템플릿 폴더가 불완전합니다: {template_dir}")

    sidebar = locate_sidebar(frontend, args.sidebar_file)
    video_source = select_video(root, args.dummy_video)
    service = detect_frontend_service(compose_path)
    workdir = detect_workdir(frontend)

    component_target = (
        frontend
        / "src"
        / "components"
        / "demo"
        / "demo-mode-console.tsx"
    )
    page_target = frontend / "src" / "app" / "demo-mode" / "page.tsx"
    compose_target = root / "compose.presentation.yaml"
    video_target = (
        root
        / "artifacts"
        / "presentation-demo"
        / "presentation-dummy.mp4"
    )
    info_target = (
        root
        / "artifacts"
        / "presentation-demo"
        / "presentation-dummy-info.json"
    )
    deploy_target = root / "scripts" / "run-presentation-demo-mode.bat"

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = (
        root
        / "artifacts"
        / "patch-backups"
        / f"presentation-demo-{stamp}"
    )
    backup.mkdir(parents=True, exist_ok=False)

    targets = [
        sidebar,
        component_target,
        page_target,
        compose_target,
        video_target,
        info_target,
        deploy_target,
    ]
    existence = backup_targets(root, backup, targets)

    try:
        component_text, _ = read_text(component_template)
        page_text, _ = read_text(page_template)
        write_text(component_target, component_text)
        write_text(page_target, page_text)

        sidebar_result = patch_sidebar(sidebar)
        video_mode = link_or_copy(video_source, video_target)

        info = {
            "generatedAt": datetime.now().isoformat(),
            "sourcePath": str(video_source),
            "targetPath": str(video_target),
            "linkMode": video_mode,
            "sizeBytes": video_target.stat().st_size,
            "sha256": sha256(video_target),
            "frontendService": service,
            "frontendWorkdir": workdir,
        }
        write_text(
            info_target,
            json.dumps(info, ensure_ascii=False, indent=2) + "\n",
        )
        write_text(
            compose_target,
            compose_override(service, workdir),
        )
        deploy_target.parent.mkdir(parents=True, exist_ok=True)
        deploy_target.write_bytes(deployment_bat(root, service))

        manifest = {
            "operation": "PRESENTATION_DEMO_MODE_PATCH",
            "createdAt": datetime.now().isoformat(),
            "root": str(root),
            "sidebar": relative(root, sidebar),
            "sidebarResult": sidebar_result,
            "dummyVideo": info,
            "targetExistence": existence,
        }
        write_text(
            backup / "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )
    except Exception:
        write_text(
            backup / "manifest.json",
            json.dumps(
                {"targetExistence": existence},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        restore(root, backup)
        raise

    print("발표용 시연 모드 패치 완료")
    print(f"백업: {backup}")
    print(f"사이드바: {sidebar}")
    print(f"더미영상 원본: {video_source}")
    print(f"더미영상 연결: {video_mode}")
    print(f"프런트엔드 서비스: {service}")
    print("")
    print("다음 명령:")
    print(r"  C:\VisionFlow-Drone\scripts\run-presentation-demo-mode.bat")
    print(r"  cd /d C:\VisionFlow-Drone\01_frontend\visionflow-web")
    print("  npm run lint")
    print("  npm run build")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=ROOT_DEFAULT)
    parser.add_argument("--dummy-video")
    parser.add_argument("--sidebar-file")
    parser.add_argument("--rollback", nargs="?", const="LATEST")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    try:
        if args.rollback is None:
            apply(args)
        else:
            backup = (
                latest_backup(root)
                if args.rollback == "LATEST"
                else Path(args.rollback).resolve()
            )
            restore(root, backup)
    except Exception as error:
        print(f"오류: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
