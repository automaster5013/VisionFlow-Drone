#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


class ReadinessError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def require_text(path: Path, needles: tuple[str, ...]) -> None:
    if not path.exists():
        raise ReadinessError(f"Required file not found: {path}")

    text = path.read_text(
        encoding="utf-8",
        errors="replace",
    )
    missing = [value for value in needles if value not in text]
    if missing:
        raise ReadinessError(
            f"{path} missing expected configuration: {missing}"
        )


def decode_certificate(path: Path) -> dict[str, object]:
    if not path.exists():
        raise ReadinessError(f"Certificate not found: {path}")

    try:
        decoded = ssl._ssl._test_decode_cert(str(path))
    except Exception as error:
        raise ReadinessError(
            f"Certificate decode failed: {path}: {error}"
        ) from error

    return decoded


def certificate_ips(decoded: dict[str, object]) -> set[str]:
    result: set[str] = set()
    for item in decoded.get("subjectAltName", ()):
        if (
            isinstance(item, tuple)
            and len(item) == 2
            and item[0] == "IP Address"
        ):
            result.add(str(item[1]))
    return result


def certificate_expiry(decoded: dict[str, object]) -> float:
    value = decoded.get("notAfter")
    if not isinstance(value, str) or not value:
        raise ReadinessError("Certificate notAfter is missing.")
    return ssl.cert_time_to_seconds(value)


def resolve_ca_file(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.exists():
            raise ReadinessError(f"CA file not found: {path}")
        return path

    try:
        result = subprocess.run(
            ["mkcert", "-CAROOT"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        raise ReadinessError(
            "mkcert Root CA could not be resolved. "
            "Install mkcert or pass --ca-file."
        ) from error

    root = result.stdout.strip()
    if not root:
        raise ReadinessError("mkcert -CAROOT returned an empty path.")

    path = Path(root) / "rootCA.pem"
    if not path.exists():
        raise ReadinessError(f"mkcert Root CA not found: {path}")
    return path


def http_probe(
    url: str,
    *,
    ssl_context: ssl.SSLContext | None = None,
) -> dict[str, object]:
    handlers: list[urllib.request.BaseHandler] = [
        urllib.request.ProxyHandler({}),
    ]
    if ssl_context is not None:
        handlers.append(
            urllib.request.HTTPSHandler(context=ssl_context)
        )

    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "VisionFlow-Readiness/1.0"},
        method="GET",
    )

    try:
        with opener.open(request, timeout=5.0) as response:
            body = response.read()
            status = int(response.status)
            headers = response.headers
    except urllib.error.HTTPError as error:
        body = error.read()
        status = int(error.code)
        headers = error.headers
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ReadinessError(
            f"HTTP probe failed: {url}: {error}"
        ) from error

    return {
        "url": url,
        "status": status,
        "body": body.decode("utf-8", errors="replace"),
        "contentType": headers.get("Content-Type"),
        "server": headers.get("Server"),
        "via": headers.get("Via"),
    }


def validate_https_runtime(
    *,
    host_ip: str,
    ca_file: Path,
) -> dict[str, object]:
    try:
        context = ssl.create_default_context(cafile=str(ca_file))
    except Exception as error:
        raise ReadinessError(
            f"Could not load CA file {ca_file}: {error}"
        ) from error

    health_url = f"https://{host_ip}:3443/healthz"
    health = http_probe(
        health_url,
        ssl_context=context,
    )
    if health["status"] != 200 or str(health["body"]).strip() != "ok":
        raise ReadinessError(
            "HTTPS health probe failed: "
            f"status={health['status']} body={health['body']!r}"
        )

    direct = http_probe(
        "http://127.0.0.1:8000/api/ingest/dji/status"
    )
    proxied = http_probe(
        f"https://{host_ip}:3443/api/ingest/dji/status",
        ssl_context=context,
    )

    if (
        direct["status"] != proxied["status"]
        or direct["body"] != proxied["body"]
    ):
        raise ReadinessError(
            "Caddy DJI proxy does not match the direct AI response: "
            f"direct=({direct['status']}, {direct['body']!r}) "
            f"proxied=({proxied['status']}, {proxied['body']!r})"
        )

    via = str(proxied.get("via") or "")
    if "caddy" not in via.lower():
        raise ReadinessError(
            "HTTPS DJI proxy response does not contain a Caddy Via header: "
            f"{via!r}"
        )

    return {
        "caFile": str(ca_file),
        "health": health,
        "directAiStatus": direct,
        "proxiedAiStatus": proxied,
        "proxyParity": True,
    }


def validate_caddy(
    *,
    root: Path,
    caddyfile: Path,
    cert_dir: Path,
) -> None:
    command = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{caddyfile}:/etc/caddy/Caddyfile:ro",
        "-v",
        f"{cert_dir}:/certs:ro",
        "caddy:2-alpine",
        "caddy",
        "validate",
        "--config",
        "/etc/caddy/Caddyfile",
    ]
    print("[CMD] " + subprocess.list2cmdline(command))
    result = subprocess.run(
        command,
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise ReadinessError(
            f"Caddy validation failed with exit={result.returncode}"
        )


def inspect_running_ai() -> dict[str, object]:
    command = [
        "docker",
        "inspect",
        "visionflow-ai",
        "--format",
        "{{json .Config.Env}}",
    ]
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {
            "available": False,
            "sourceType": None,
            "djiInputMode": None,
        }

    try:
        values = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        values = []

    env: dict[str, str] = {}
    for value in values:
        if not isinstance(value, str) or "=" not in value:
            continue
        key, item = value.split("=", 1)
        env[key] = item

    return {
        "available": True,
        "sourceType": env.get("AI_SOURCE_TYPE"),
        "djiInputMode": env.get("AI_DJI_INPUT_MODE"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "VisionFlow Phase 3 DJI Android HTTPS/network "
            "readiness gate."
        )
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--host-ip", required=True)
    parser.add_argument(
        "--ca-file",
        default=None,
        help=(
            "Trusted CA PEM for the mobile HTTPS certificate. "
            "Defaults to mkcert -CAROOT/rootCA.pem."
        ),
    )
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    host_ip = args.host_ip.strip()
    if not host_ip:
        print("[FAIL] --host-ip must not be empty", file=sys.stderr)
        return 2

    cert_dir = root / "artifacts" / "mobile-https" / "certs"
    cert = cert_dir / "visionflow-mobile.pem"
    caddyfile = root / "infrastructure" / "mobile-https" / "Caddyfile"
    manifest = (
        root
        / "04_android"
        / "visionflow-dji-bridge"
        / "app"
        / "src"
        / "main"
        / "AndroidManifest.xml"
    )
    network_security = (
        root
        / "04_android"
        / "visionflow-dji-bridge"
        / "app"
        / "src"
        / "main"
        / "res"
        / "xml"
        / "network_security_config.xml"
    )
    compose_dji = root / "compose.dji-bridge.yaml"

    evidence_dir = (
        root
        / "artifacts"
        / "phase3-dji-network-readiness"
        / run_id()
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    summary_path = evidence_dir / "summary.json"

    summary: dict[str, object] = {
        "gate": "phase3-dji-network-readiness",
        "status": "FAIL",
        "hostIp": host_ip,
        "completedAt": None,
        "certificate": {},
        "caddy": {},
        "android": {},
        "compose": {},
        "runtime": {},
        "androidUserCaInstalled": "WAIT",
        "physicalDjiRuntime": "SKIPPED",
        "aws": "SKIPPED",
    }

    try:
        print("=== VISIONFLOW PHASE 3 DJI NETWORK READINESS ===")
        print(f"root={root}")
        print(f"hostIp={host_ip}")

        decoded = decode_certificate(cert)
        ips = certificate_ips(decoded)
        expires_at = certificate_expiry(decoded)
        if host_ip not in ips:
            raise ReadinessError(
                "Current host IP is not present in certificate SAN: "
                f"hostIp={host_ip}, certificateIps={sorted(ips)}"
            )
        if expires_at <= datetime.now(timezone.utc).timestamp():
            raise ReadinessError("Mobile HTTPS certificate has expired.")

        summary["certificate"] = {
            "path": str(cert),
            "sanIps": sorted(ips),
            "notAfter": decoded.get("notAfter"),
            "hostIpMatched": True,
        }
        print("[PASS] Certificate SAN includes current host IP")

        require_text(
            caddyfile,
            (
                "@dji_ai_ingest path /api/ingest/dji/*",
                "reverse_proxy @dji_ai_ingest host.docker.internal:8000",
            ),
        )
        validate_caddy(
            root=root,
            caddyfile=caddyfile,
            cert_dir=cert_dir,
        )
        ca_file = resolve_ca_file(args.ca_file)
        runtime_https = validate_https_runtime(
            host_ip=host_ip,
            ca_file=ca_file,
        )
        summary["caddy"] = {
            "route": "/api/ingest/dji/* -> host.docker.internal:8000",
            "validated": True,
            "runtimeHttps": runtime_https,
        }
        print("[PASS] Caddy DJI AI route and syntax")
        print("[PASS] HTTPS health probe with trusted mkcert CA")
        print("[PASS] Caddy -> AI DJI route runtime proxy parity")

        require_text(
            manifest,
            (
                'android:networkSecurityConfig="@xml/network_security_config"',
                'android:usesCleartextTraffic="false"',
            ),
        )
        require_text(
            network_security,
            (
                'cleartextTrafficPermitted="false"',
                "<debug-overrides>",
                '<certificates src="user" />',
            ),
        )
        summary["android"] = {
            "cleartextPermitted": False,
            "debugUserCaTrustConfigured": True,
        }
        print("[PASS] Android cleartext disabled")
        print("[PASS] Android debug user-CA trust configured")

        require_text(
            compose_dji,
            (
                "AI_SOURCE_TYPE: DJI_LIVE",
                "AI_DJI_INPUT_MODE: ANDROID_BRIDGE",
                "AI_DJI_BRIDGE_FFMPEG:",
                "VISIONFLOW_DJI_BRIDGE_KEY:",
            ),
        )
        summary["compose"] = {
            "djiOverride": str(compose_dji),
            "sourceType": "DJI_LIVE",
            "inputMode": "ANDROID_BRIDGE",
            "dedicatedBridgeKeyRequired": True,
        }
        print("[PASS] DJI compose override configured")
        print("[PASS] DJI compose override requires dedicated bridge key")

        runtime = inspect_running_ai()
        summary["runtime"] = runtime
        if (
            runtime.get("sourceType") == "DJI_LIVE"
            and runtime.get("djiInputMode") == "ANDROID_BRIDGE"
        ):
            print("[PASS] Running AI is already in DJI Android Bridge mode")
        else:
            print(
                "[WAIT] Running AI remains in current non-DJI profile; "
                "switch is intentionally deferred."
            )

        summary["status"] = "PASS"
        summary["completedAt"] = utc_now()
        print("")
        print("=== PHASE 3 DJI NETWORK READINESS: PASS ===")
        print("httpsProxy=PASS")
        print("httpsRuntime=PASS")
        print("caddyAiProxyRuntime=PASS")
        print("certificateSan=PASS")
        print("androidCleartext=DENIED")
        print("androidDebugUserCaTrust=CONFIGURED")
        print("runtimeDjiMode=WAIT_OR_PASS")
        print("androidUserCaInstalled=WAIT")
        print("physicalDJI=SKIPPED")
        print(f"evidence={summary_path}")
        return 0

    except ReadinessError as error:
        summary["error"] = str(error)
        summary["completedAt"] = utc_now()
        print(f"[FAIL] {error}", file=sys.stderr)
        return 1

    finally:
        summary_path.write_text(
            json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    raise SystemExit(main())
