#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SESSION_HEADER = "X-VisionFlow-Operator-Session"


class GateError(RuntimeError):
    pass


@dataclass(frozen=True)
class Account:
    username: str
    role: str
    password_env: str


@dataclass
class ActiveSession:
    account: Account
    token: str


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="VisionFlow Phase 3 operator account/RBAC E2E gate."
    )
    p.add_argument("--backend-url", default="http://127.0.0.1:8080")
    p.add_argument("--frontend-url", default="http://127.0.0.1:3000")
    p.add_argument("--drone-id", type=int, default=1)
    p.add_argument("--viewer-username", default=os.getenv("VISIONFLOW_E2E_VIEWER_USERNAME", "viewer"))
    p.add_argument("--operator-username", default=os.getenv("VISIONFLOW_E2E_OPERATOR_USERNAME", "operator"))
    p.add_argument("--admin-username", default=os.getenv("VISIONFLOW_E2E_ADMIN_USERNAME", "admin"))
    p.add_argument(
        "--evidence",
        default="artifacts/phase3-auth-e2e/latest-summary.json",
    )
    return p.parse_args()


def decode(data: bytes) -> Any:
    if not data:
        return None
    text = data.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def http(
    method: str,
    url: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers[SESSION_HEADER] = token
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")

    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=8) as res:
            return res.status, decode(res.read())
    except HTTPError as err:
        return err.code, decode(err.read())
    except URLError as err:
        raise GateError(f"{method} {url} connection failed: {err}") from err


def find(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        if key in payload:
            return payload[key]
        for value in payload.values():
            found = find(value, key)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = find(value, key)
            if found is not None:
                return found
    return None


def expect(label: str, actual: int, *expected: int) -> None:
    if actual not in expected:
        raise GateError(
            f"{label}: expected HTTP {expected}, actual HTTP {actual}"
        )
    print(f"[PASS] {label} - HTTP {actual}", flush=True)


def password_for(account: Account) -> str:
    value = os.getenv(account.password_env)
    if value:
        return value
    value = getpass.getpass(
        f"{account.role} account '{account.username}' password: "
    )
    if not value:
        raise GateError(f"{account.role} password is empty")
    return value


def login(backend: str, account: Account) -> ActiveSession:
    password = password_for(account)
    status, payload = http(
        "POST",
        f"{backend}/api/security/sessions",
        body={"username": account.username, "password": password},
    )
    password = ""
    expect(f"{account.role} password login", status, 200)

    token = str(find(payload, "token") or "").strip()
    username = str(find(payload, "username") or "").strip()
    role = str(find(payload, "role") or "").strip().upper()
    change_required = find(payload, "passwordChangeRequired")

    if len(token) < 40:
        raise GateError(f"{account.role}: invalid session token in login response")
    if username != account.username:
        raise GateError(
            f"{account.role}: username mismatch expected={account.username} actual={username}"
        )
    if role != account.role:
        raise GateError(
            f"{account.role}: role mismatch actual={role}"
        )
    if change_required is not False:
        raise GateError(
            f"{account.role}: passwordChangeRequired={change_required}; "
            "initial password rotation must already be complete"
        )

    print(f"[PASS] {account.role} DB role auto-application", flush=True)
    print(f"[PASS] {account.role} initial password rotation complete", flush=True)
    return ActiveSession(account, token)


def verify_me(backend: str, session: ActiveSession) -> None:
    status, payload = http(
        "GET",
        f"{backend}/api/security/me",
        token=session.token,
    )
    expect(f"{session.account.role} /api/security/me", status, 200)

    if find(payload, "authenticated") is not True:
        raise GateError(f"{session.account.role}: /me not authenticated")
    if str(find(payload, "username") or "") != session.account.username:
        raise GateError(f"{session.account.role}: /me username mismatch")
    if str(find(payload, "role") or "").upper() != session.account.role:
        raise GateError(f"{session.account.role}: /me role mismatch")
    print(f"[PASS] {session.account.role} session principal correlation")


def verify_boundaries(
    backend: str,
    drone_id: int,
    session: ActiveSession,
) -> None:
    role = session.account.role

    status, _ = http(
        "GET",
        f"{backend}/api/drones/{drone_id}",
        token=session.token,
    )
    expect(f"{role} drone read", status, 200)

    status, _ = http(
        "GET",
        f"{backend}/api/security/sessions",
        token=session.token,
    )
    if role == "ADMIN":
        expect("ADMIN session-list boundary", status, 200)
    else:
        expect(f"{role} admin boundary denied", status, 403)

    # Safe authorization probe: droneId=0 is invalid. VIEWER should be
    # rejected by Spring Security; OPERATOR/ADMIN should pass authorization
    # and then fail safely in validation/controller logic without DB creation.
    status, _ = http(
        "POST",
        f"{backend}/api/drones/0/flight-sessions",
        token=session.token,
        body={},
    )
    if role == "VIEWER":
        expect("VIEWER operator mutation denied", status, 403)
    else:
        if status in (401, 403):
            raise GateError(
                f"{role}: operator mutation authorization denied HTTP {status}"
            )
        if not 400 <= status < 500:
            raise GateError(
                f"{role}: expected safe controller 4xx, actual HTTP {status}"
            )
        print(
            f"[PASS] {role} operator mutation authorization - safe HTTP {status}"
        )


def verify_public_boundaries(backend: str, frontend: str, drone_id: int) -> None:
    status, _ = http("GET", f"{backend}/actuator/health")
    expect("Backend health", status, 200)

    for path in ("/operator-login", "/operator-password-change"):
        status, _ = http("GET", f"{frontend}{path}")
        expect(f"Frontend route {path}", status, 200)

    status, _ = http("GET", f"{backend}/api/drones/{drone_id}")
    expect("Unauthenticated drone read denied", status, 401)

    status, _ = http(
        "GET",
        f"{backend}/api/drones/{drone_id}",
        token="invalid-phase3-session-token",
    )
    expect("Invalid session token denied", status, 401)


def logout(backend: str, drone_id: int, session: ActiveSession) -> None:
    role = session.account.role
    status, _ = http(
        "DELETE",
        f"{backend}/api/security/sessions/current",
        token=session.token,
    )
    expect(f"{role} logout", status, 204)

    status, _ = http(
        "GET",
        f"{backend}/api/drones/{drone_id}",
        token=session.token,
    )
    expect(f"{role} revoked session rejected", status, 401)


def save(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    a = args()
    backend = a.backend_url.rstrip("/")
    frontend = a.frontend_url.rstrip("/")
    evidence = Path(a.evidence)
    if not evidence.is_absolute():
        evidence = Path.cwd() / evidence

    if a.drone_id < 1:
        print("[FAIL] --drone-id must be >= 1", file=sys.stderr)
        return 2

    accounts = (
        Account(a.viewer_username, "VIEWER", "VISIONFLOW_E2E_VIEWER_PASSWORD"),
        Account(a.operator_username, "OPERATOR", "VISIONFLOW_E2E_OPERATOR_PASSWORD"),
        Account(a.admin_username, "ADMIN", "VISIONFLOW_E2E_ADMIN_PASSWORD"),
    )
    sessions: list[ActiveSession] = []
    summary = {
        "gate": "phase3-auth-rbac-e2e",
        "status": "FAIL",
        "backendUrl": backend,
        "frontendUrl": frontend,
        "droneId": a.drone_id,
        "accounts": [
            {"username": x.username, "expectedRole": x.role}
            for x in accounts
        ],
        "passwordsStored": False,
        "sessionTokensStored": False,
    }

    try:
        print("=== VISIONFLOW PHASE 3 AUTH/RBAC E2E GATE ===")
        print("[INFO] Passwords and session tokens are never written to Evidence.")

        verify_public_boundaries(backend, frontend, a.drone_id)

        for account in accounts:
            print(f"\n[STEP] {account.role} account")
            session = login(backend, account)
            sessions.append(session)
            verify_me(backend, session)
            verify_boundaries(backend, a.drone_id, session)

        print("\n[STEP] Session logout/revocation")
        for session in reversed(sessions):
            logout(backend, a.drone_id, session)
        sessions.clear()

        summary["status"] = "PASS"
        save(evidence, summary)

        print("\n=== PHASE 3 AUTH/RBAC E2E GATE: PASS ===")
        print("roles=VIEWER,OPERATOR,ADMIN")
        print("passwordChangeRequired=false")
        print("adminBoundary=PASS")
        print("operatorBoundary=PASS")
        print("sessionRevocation=PASS")
        print(f"evidence={evidence}")
        return 0

    except GateError as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        summary["error"] = str(error)
        save(evidence, summary)

        for session in reversed(sessions):
            try:
                http(
                    "DELETE",
                    f"{backend}/api/security/sessions/current",
                    token=session.token,
                )
            except GateError:
                pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
