"""Safely switch VisionFlow frontend between presentation HTTP and mobile HTTPS."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import ssl
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


PRESENTATION_READY = "PRESENTATION_HTTP_READY"
MOBILE_READY = "MOBILE_HTTPS_READY"
STOPPED = "FRONTEND_STOPPED"
PORT_CONFLICT = "PORT_3000_CONFLICT"
AMBIGUOUS = "FRONTEND_MODE_AMBIGUOUS"
FRONTEND_PORT = 3000
FRONTEND_SERVICE_CANDIDATES = ("frontend-web", "frontend")


class RuntimeModeError(RuntimeError):
    """Raised when a safe runtime mode transition cannot be completed."""


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    status_code: int | None = None
    error: str | None = None


@dataclass(frozen=True)
class RuntimeState:
    mode: str
    http: ProbeResult
    https: ProbeResult
    listening_pids: tuple[int, ...]


def probe_endpoint(
    *,
    https: bool,
    host: str = "127.0.0.1",
    port: int = FRONTEND_PORT,
    path: str = "/dashboard",
    timeout: float = 8.0,
) -> ProbeResult:
    connection: http.client.HTTPConnection | http.client.HTTPSConnection
    try:
        if https:
            context = ssl._create_unverified_context()
            connection = http.client.HTTPSConnection(
                host,
                port,
                timeout=timeout,
                context=context,
            )
        else:
            connection = http.client.HTTPConnection(host, port, timeout=timeout)
        connection.request("GET", path, headers={"Connection": "close"})
        response = connection.getresponse()
        response.read(1024)
        return ProbeResult(
            ok=200 <= response.status < 400,
            status_code=response.status,
        )
    except (OSError, http.client.HTTPException, ssl.SSLError) as error:
        return ProbeResult(ok=False, error=type(error).__name__)
    finally:
        if "connection" in locals():
            connection.close()


def listening_pids(port: int = FRONTEND_PORT) -> tuple[int, ...]:
    if os.name != "nt":
        return ()
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    values: set[int] = set()
    suffix = f":{port}"
    for line in result.stdout.splitlines():
        columns = line.split()
        if len(columns) < 5 or columns[0].upper() != "TCP":
            continue
        if not columns[1].endswith(suffix) or columns[3].upper() != "LISTENING":
            continue
        try:
            values.add(int(columns[4]))
        except ValueError:
            continue
    return tuple(sorted(values))


def classify_state(
    http: ProbeResult,
    https: ProbeResult,
    pids: Sequence[int],
) -> str:
    if http.ok and not https.ok:
        return PRESENTATION_READY
    if https.ok and not http.ok:
        return MOBILE_READY
    if http.ok and https.ok:
        return AMBIGUOUS
    if pids:
        return PORT_CONFLICT
    return STOPPED


def inspect_state() -> RuntimeState:
    http = probe_endpoint(https=False)
    https = probe_endpoint(https=True)
    pids = listening_pids()
    return RuntimeState(
        mode=classify_state(http, https, pids),
        http=http,
        https=https,
        listening_pids=pids,
    )


def compose_base(root: Path) -> list[str]:
    compose = root / "compose.yaml"
    environment = root / ".env.docker"
    if not compose.is_file():
        raise RuntimeModeError(f"Compose 파일이 없습니다: {compose}")
    if not environment.is_file():
        raise RuntimeModeError(f"Docker 환경 파일이 없습니다: {environment}")
    return [
        "docker",
        "compose",
        "--env-file",
        str(environment),
        "-f",
        str(compose),
    ]


def run_command(
    arguments: Sequence[str],
    *,
    root: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(arguments),
            cwd=root,
            check=check,
            text=True,
        )
    except FileNotFoundError as error:
        raise RuntimeModeError(f"명령을 찾을 수 없습니다: {arguments[0]}") from error
    except subprocess.CalledProcessError as error:
        raise RuntimeModeError(
            f"명령 실행에 실패했습니다(exit={error.returncode}): "
            + " ".join(arguments)
        ) from error


def resolve_frontend_service(root: Path) -> str:
    result = subprocess.run(
        [*compose_base(root), "config", "--services"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeModeError("Compose 서비스 목록을 읽을 수 없습니다.")
    services = {item.strip() for item in result.stdout.splitlines() if item.strip()}
    for candidate in FRONTEND_SERVICE_CANDIDATES:
        if candidate in services:
            return candidate
    raise RuntimeModeError(
        "Compose에서 프런트엔드 서비스를 찾을 수 없습니다. "
        f"확인된 서비스: {', '.join(sorted(services)) or '-'}"
    )


def wait_for_mode(expected: str, timeout_seconds: float) -> RuntimeState:
    deadline = time.monotonic() + timeout_seconds
    last = inspect_state()
    while time.monotonic() < deadline:
        if last.mode == expected:
            return last
        time.sleep(1)
        last = inspect_state()
    raise RuntimeModeError(
        f"{timeout_seconds:g}초 안에 {expected} 상태가 되지 않았습니다. "
        f"현재 상태: {last.mode}"
    )


def format_state(state: RuntimeState) -> str:
    pid_value = ", ".join(str(item) for item in state.listening_pids) or "-"
    http_value = (
        f"HTTP {state.http.status_code}"
        if state.http.status_code is not None
        else f"실패({state.http.error or '-'})"
    )
    https_value = (
        f"HTTP {state.https.status_code}"
        if state.https.status_code is not None
        else f"실패({state.https.error or '-'})"
    )
    return (
        f"VisionFlow frontend mode: {state.mode}\n"
        f"HTTP probe : {http_value}\n"
        f"HTTPS probe: {https_value}\n"
        f"Port 3000 PID: {pid_value}"
    )


def ensure_presentation(
    root: Path,
    *,
    build: bool,
    timeout_seconds: float,
) -> RuntimeState:
    state = inspect_state()
    if state.mode == PRESENTATION_READY:
        return state
    if state.mode in {MOBILE_READY, PORT_CONFLICT, AMBIGUOUS}:
        pids = ", ".join(str(item) for item in state.listening_pids) or "확인 불가"
        raise RuntimeModeError(
            "포트 3000이 다른 실행 모드에서 사용 중입니다. "
            "스마트폰 HTTPS 서버를 실행한 창에서 Ctrl+C로 종료한 뒤 "
            f"다시 실행하세요. PID: {pids}"
        )
    service = resolve_frontend_service(root)
    command = [*compose_base(root), "up", "-d"]
    if build:
        command.append("--build")
    command.append(service)
    run_command(command, root=root)
    return wait_for_mode(PRESENTATION_READY, timeout_seconds)


def wait_until_port_free(timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        state = inspect_state()
        if state.mode == STOPPED:
            return
        time.sleep(1)
    state = inspect_state()
    pids = ", ".join(str(item) for item in state.listening_pids) or "확인 불가"
    raise RuntimeModeError(
        f"포트 3000이 해제되지 않았습니다. 현재 {state.mode}, PID: {pids}"
    )


def run_mobile(
    root: Path,
    *,
    lan_ip: str | None,
    force_certificate: bool,
    configure_firewall: bool,
    skip_setup: bool,
) -> int:
    state = inspect_state()
    if state.mode == MOBILE_READY:
        print(format_state(state))
        print("스마트폰 HTTPS 모드가 이미 실행 중입니다.")
        return 0
    if state.mode == PRESENTATION_READY:
        service = resolve_frontend_service(root)
        run_command([*compose_base(root), "stop", service], root=root)
        wait_until_port_free()
    elif state.mode in {PORT_CONFLICT, AMBIGUOUS}:
        pids = ", ".join(str(item) for item in state.listening_pids) or "확인 불가"
        raise RuntimeModeError(
            "Docker HTTP 프런트엔드가 아닌 프로세스가 포트 3000을 사용 중입니다. "
            f"직접 확인 후 종료하세요. PID: {pids}"
        )

    launcher = root / "scripts" / "run-visionflow-mobile-https.bat"
    if not launcher.is_file():
        raise RuntimeModeError(f"모바일 HTTPS 실행기가 없습니다: {launcher}")
    arguments = ["cmd.exe", "/d", "/c", "call", str(launcher)]
    if lan_ip:
        arguments.extend(["-LanIp", lan_ip])
    if force_certificate:
        arguments.append("-ForceCertificate")
    if configure_firewall:
        arguments.append("-ConfigureFirewall")
    if skip_setup:
        arguments.append("-SkipSetup")
    print("VisionFlow frontend mode: STARTING_MOBILE_HTTPS")
    print("종료할 때는 이 창에서 Ctrl+C를 누르세요.")
    result = run_command(arguments, root=root, check=False)
    return result.returncode


def build_parser(default_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VisionFlow HTTP/HTTPS frontend mode switch"
    )
    parser.add_argument("--root", default=str(default_root))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="현재 프런트엔드 모드 확인")
    presentation = subparsers.add_parser(
        "presentation",
        help="Docker 발표용 HTTP 프런트엔드 시작",
    )
    presentation.add_argument("--build", action="store_true")
    presentation.add_argument("--timeout-seconds", type=float, default=120.0)
    mobile = subparsers.add_parser(
        "mobile",
        help="스마트폰 실센서용 HTTPS 프런트엔드 시작",
    )
    mobile.add_argument("--lan-ip")
    mobile.add_argument("--force-certificate", action="store_true")
    mobile.add_argument("--configure-firewall", action="store_true")
    mobile.add_argument("--skip-setup", action="store_true")
    return parser


def main(arguments: Iterable[str] | None = None) -> int:
    default_root = Path(__file__).resolve().parent.parent
    parser = build_parser(default_root)
    args = parser.parse_args(arguments)
    root = Path(args.root).resolve()
    try:
        if args.command == "status":
            state = inspect_state()
            print(format_state(state))
            return 0 if state.mode in {PRESENTATION_READY, MOBILE_READY, STOPPED} else 1
        if args.command == "presentation":
            if args.timeout_seconds <= 0:
                raise RuntimeModeError("대기 시간은 양수여야 합니다.")
            state = ensure_presentation(
                root,
                build=args.build,
                timeout_seconds=args.timeout_seconds,
            )
            print(format_state(state))
            print("Dashboard: http://localhost:3000/dashboard")
            return 0
        return run_mobile(
            root,
            lan_ip=args.lan_ip,
            force_certificate=args.force_certificate,
            configure_firewall=args.configure_firewall,
            skip_setup=args.skip_setup,
        )
    except RuntimeModeError as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
