#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


RFC1918_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)
DEFAULT_PORT = 3443
DEFAULT_INTERVAL_SECONDS = 5.0


class RuntimeAgentError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def is_lan_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False

    return (
        address.version == 4
        and any(address in network for network in RFC1918_NETWORKS)
    )


def default_route_ipv4() -> str | None:
    for target in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(target)
            candidate = str(sock.getsockname()[0])
            if is_lan_ipv4(candidate):
                return candidate
        except OSError:
            pass
        finally:
            sock.close()

    return None


def local_ipv4_candidates() -> tuple[list[str], str | None]:
    preferred = default_route_ipv4()
    result: list[str] = []

    if preferred:
        result.append(preferred)

    try:
        infos = socket.getaddrinfo(
            socket.gethostname(),
            None,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror:
        infos = []

    for info in infos:
        candidate = str(info[4][0])
        if is_lan_ipv4(candidate) and candidate not in result:
            result.append(candidate)

    return result, preferred


def decode_certificate(path: Path) -> dict[str, object]:
    try:
        return ssl._ssl._test_decode_cert(str(path))
    except Exception as error:
        raise RuntimeAgentError(
            f"mobile HTTPS certificate decode failed: {error}"
        ) from error


def certificate_ips(decoded: dict[str, object]) -> list[str]:
    result: list[str] = []

    for item in decoded.get("subjectAltName", ()):
        if (
            isinstance(item, tuple)
            and len(item) == 2
            and item[0] == "IP Address"
            and is_lan_ipv4(str(item[1]))
        ):
            result.append(str(item[1]))

    return sorted(set(result))


def certificate_expired(decoded: dict[str, object]) -> bool:
    value = decoded.get("notAfter")
    if not isinstance(value, str) or not value:
        return True

    try:
        return ssl.cert_time_to_seconds(value) <= time.time()
    except ValueError:
        return True


def resolve_mkcert_ca() -> Path:
    result = subprocess.run(
        ["mkcert", "-CAROOT"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    root = result.stdout.strip()
    if not root:
        raise RuntimeAgentError(
            "mkcert -CAROOT returned an empty path"
        )

    path = Path(root) / "rootCA.pem"
    if not path.is_file():
        raise RuntimeAgentError(
            f"mkcert root CA not found: {path}"
        )
    return path


def probe_https_health(
    origin: str,
    ca_file: Path,
) -> dict[str, object]:
    url = f"{origin}/healthz"
    context = ssl.create_default_context(cafile=str(ca_file))
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context),
    )
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "VisionFlow-MobileRuntime/1.0"},
    )

    try:
        with opener.open(request, timeout=4.0) as response:
            body = response.read(256).decode(
                "utf-8",
                errors="replace",
            )
            status = int(response.status)
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        ssl.SSLError,
    ) as error:
        return {
            "status": "FAIL",
            "url": url,
            "httpStatus": None,
            "error": str(error),
        }

    if status == 200 and body.strip() == "ok":
        return {
            "status": "PASS",
            "url": url,
            "httpStatus": status,
            "error": None,
        }

    return {
        "status": "FAIL",
        "url": url,
        "httpStatus": status,
        "error": f"unexpected health response: {body[:120]!r}",
    }


def build_profile(
    *,
    root: Path,
    port: int,
    explicit_host_ip: str | None = None,
) -> dict[str, object]:
    candidates, preferred = local_ipv4_candidates()

    if explicit_host_ip:
        if not is_lan_ipv4(explicit_host_ip):
            raise RuntimeAgentError(
                "--host-ip must be an RFC1918 IPv4 address"
            )
        host_ip = explicit_host_ip
        if host_ip not in candidates:
            candidates.insert(0, host_ip)
        detection_source = "explicit"
    else:
        host_ip = preferred or (candidates[0] if candidates else None)
        detection_source = (
            "udp-default-route"
            if preferred
            else "hostname-address"
            if host_ip
            else None
        )

    cert_path = (
        root
        / "artifacts"
        / "mobile-https"
        / "certs"
        / "visionflow-mobile.pem"
    )
    certificate: dict[str, object] = {
        "available": False,
        "sanMatch": False,
        "sanIps": [],
        "notAfter": None,
        "expired": False,
    }
    https: dict[str, object] = {
        "status": "UNKNOWN",
        "url": None,
        "httpStatus": None,
        "error": None,
    }

    origin = (
        f"https://{host_ip}:{port}"
        if host_ip is not None
        else None
    )
    ready = False

    if host_ip is None:
        message = (
            "Windows host의 RFC1918 LAN IPv4를 자동 감지하지 못했습니다."
        )
    elif not cert_path.is_file():
        message = (
            "현재 LAN IP는 감지했지만 mobile HTTPS 인증서가 없습니다."
        )
    else:
        decoded = decode_certificate(cert_path)
        san_ips = certificate_ips(decoded)
        expired = certificate_expired(decoded)
        not_after = decoded.get("notAfter")
        san_match = host_ip in san_ips

        certificate = {
            "available": True,
            "sanMatch": san_match,
            "sanIps": san_ips,
            "notAfter": (
                str(not_after)
                if isinstance(not_after, str)
                else None
            ),
            "expired": expired,
        }

        if expired:
            https = {
                "status": "BLOCKED",
                "url": f"{origin}/healthz",
                "httpStatus": None,
                "error": "mobile HTTPS certificate is expired",
            }
            message = "mobile HTTPS 인증서가 만료되었습니다."
        elif not san_match:
            https = {
                "status": "BLOCKED",
                "url": f"{origin}/healthz",
                "httpStatus": None,
                "error": (
                    "current host IP is not present in certificate SAN"
                ),
            }
            message = (
                f"현재 LAN IP {host_ip}가 인증서 SAN에 없습니다. "
                "QR 생성 전에 인증서를 갱신하세요."
            )
        else:
            try:
                ca_file = resolve_mkcert_ca()
                https = probe_https_health(origin, ca_file)
            except (
                RuntimeAgentError,
                FileNotFoundError,
                subprocess.CalledProcessError,
            ) as error:
                https = {
                    "status": "FAIL",
                    "url": f"{origin}/healthz",
                    "httpStatus": None,
                    "error": str(error),
                }

            ready = https["status"] == "PASS"
            message = (
                "현재 LAN HTTPS 주소, 인증서 SAN, /healthz 확인 완료."
                if ready
                else "현재 LAN HTTPS /healthz 검증에 실패했습니다."
            )

    return {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "hostIp": host_ip,
        "candidateIps": candidates,
        "origin": origin,
        "port": port,
        "detectionSource": detection_source,
        "ready": ready,
        "message": message,
        "certificate": certificate,
        "https": https,
    }


def write_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def acquire_watch_lock(runtime_dir: Path):
    runtime_dir.mkdir(parents=True, exist_ok=True)
    lock_path = runtime_dir / "agent.lock"
    handle = lock_path.open("a+b")

    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()

    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(
                handle.fileno(),
                msvcrt.LK_NBLCK,
                1,
            )
        else:
            import fcntl

            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
    except OSError as error:
        handle.close()
        raise RuntimeAgentError(
            "Mobile HTTPS Runtime Agent is already running"
        ) from error

    return handle


def emit_profile(
    *,
    root: Path,
    output: Path,
    port: int,
    explicit_host_ip: str | None,
) -> dict[str, object]:
    profile = build_profile(
        root=root,
        port=port,
        explicit_host_ip=explicit_host_ip,
    )
    write_atomic(output, profile)

    state = "READY" if profile["ready"] else "BLOCKED"
    print(
        f"[{state}] origin={profile['origin'] or 'unavailable'} "
        f"message={profile['message']}",
        flush=True,
    )
    return profile


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "VisionFlow Windows host LAN/mobile HTTPS runtime detector."
        )
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--host-ip", default=None)
    parser.add_argument(
        "--port",
        type=int,
        default=int(
            os.getenv(
                "VISIONFLOW_MOBILE_HTTPS_PORT",
                str(DEFAULT_PORT),
            )
        ),
    )
    parser.add_argument(
        "--watch",
        action="store_true",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
    )
    args = parser.parse_args()

    if not 1 <= args.port <= 65_535:
        parser.error("--port must be in 1..65535")
    if args.interval_seconds < 1:
        parser.error("--interval-seconds must be at least 1")

    root = Path(args.repo_root).resolve()
    runtime_dir = (
        root / "artifacts" / "mobile-https" / "runtime"
    )
    output = runtime_dir / "network-profile.json"

    if not args.watch:
        try:
            emit_profile(
                root=root,
                output=output,
                port=args.port,
                explicit_host_ip=args.host_ip,
            )
            print(f"profile={output}")
            return 0
        except RuntimeAgentError as error:
            print(f"[FAIL] {error}", file=sys.stderr)
            return 1

    try:
        lock_handle = acquire_watch_lock(runtime_dir)
    except RuntimeAgentError as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1

    pid_path = runtime_dir / "agent.pid"
    pid_path.write_text(
        str(os.getpid()) + "\n",
        encoding="ascii",
    )

    print(
        "=== VISIONFLOW MOBILE HTTPS RUNTIME AGENT ===",
        flush=True,
    )
    print(f"root={root}", flush=True)
    print(f"profile={output}", flush=True)
    print(
        f"intervalSeconds={args.interval_seconds}",
        flush=True,
    )

    try:
        while True:
            try:
                emit_profile(
                    root=root,
                    output=output,
                    port=args.port,
                    explicit_host_ip=args.host_ip,
                )
            except RuntimeAgentError as error:
                print(f"[WAIT] {error}", file=sys.stderr, flush=True)

            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        print("Runtime Agent stopped.", flush=True)
        return 0
    finally:
        try:
            pid_path.unlink(missing_ok=True)
        finally:
            lock_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
