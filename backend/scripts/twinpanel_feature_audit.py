#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

CURRENT = Path("/opt/twinpanel/current")
BACKEND_ENV = Path("/etc/twinpanel/backend.env")
FRONTEND_ENV = Path("/etc/twinpanel/frontend.env")
INSTALL_ENV = Path("/etc/twinpanel/install.env")


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


# Load the exact installed runtime environment before importing TwinPanel.
for env_path in (INSTALL_ENV, BACKEND_ENV, FRONTEND_ENV):
    for key, value in load_env_file(env_path).items():
        os.environ.setdefault(key, value)

# The script is shipped inside backend/scripts and may be called from anywhere.
backend_dir = CURRENT / "backend"
if backend_dir.is_dir():
    sys.path.insert(0, str(backend_dir))


@dataclass
class Result:
    name: str
    status: str
    detail: str
    elapsed_ms: int = 0


RESULTS: list[Result] = []


def record(name: str, status: str, detail: str, started: float | None = None) -> None:
    elapsed = int((time.monotonic() - started) * 1000) if started is not None else 0
    RESULTS.append(Result(name=name, status=status, detail=detail, elapsed_ms=elapsed))


def request_json(url: str, token: str | None = None, timeout: float = 6.0) -> tuple[int, Any, dict[str, str]]:
    headers = {"User-Agent": "TwinPanel-Installed-Feature-Audit/1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            try:
                payload: Any = json.loads(raw) if raw else None
            except Exception:
                payload = raw
            return response.status, payload, {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else None
        except Exception:
            payload = raw
        return exc.code, payload, {k.lower(): v for k, v in exc.headers.items()}


def unit_state(unit: str) -> str:
    cp = subprocess.run(
        ["systemctl", "is-active", unit],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
    )
    return (cp.stdout or "").strip() or "missing/inactive"


def make_admin_token() -> tuple[str | None, str]:
    try:
        from app.database import SessionLocal
        from app.models import User, UserRole
        from app.security import create_access_token

        db = SessionLocal()
        try:
            admin = (
                db.query(User)
                .filter(User.role == UserRole.ADMIN, User.is_active.is_(True))
                .order_by(User.id.asc())
                .first()
            )
            if not admin:
                return None, "no active admin user found"
            return create_access_token(str(admin.id)), f"admin_id={admin.id}"
        finally:
            db.close()
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def openapi_paths(api_base: str) -> dict[str, Any]:
    status, payload, _ = request_json(f"{api_base}/openapi.json", timeout=8)
    if status == 200 and isinstance(payload, dict) and isinstance(payload.get("paths"), dict):
        return payload["paths"]
    try:
        from app.main import app
        spec = app.openapi()
        paths = spec.get("paths") if isinstance(spec, dict) else None
        return paths if isinstance(paths, dict) else {}
    except Exception:
        return {}


def detail_text(payload: Any) -> str:
    if isinstance(payload, dict):
        if "detail" in payload:
            return str(payload.get("detail"))[:160]
        if "message" in payload:
            return str(payload.get("message"))[:160]
        keys = ",".join(list(payload.keys())[:6])
        return f"json:{keys}" if keys else "json:{}"
    if isinstance(payload, list):
        return f"list[{len(payload)}]"
    value = str(payload or "").replace("\n", " ").strip()
    return value[:160] or "empty response"


def safe_get_feature(name: str, path: str, api_base: str, token: str, paths: dict[str, Any]) -> None:
    started = time.monotonic()
    operations = paths.get(path)
    if not isinstance(operations, dict):
        record(name, "FAIL", f"route missing: GET {path}", started)
        return
    if "get" not in {str(key).lower() for key in operations}:
        record(name, "WARN", f"route exists but has no safe GET: {path}", started)
        return
    status, payload, _ = request_json(f"{api_base}{path}", token=token)
    if 200 <= status < 300:
        record(name, "PASS", f"HTTP {status} · {detail_text(payload)}", started)
    elif status in {401, 403}:
        record(name, "FAIL", f"admin auth rejected: HTTP {status} · {detail_text(payload)}", started)
    elif status == 422:
        record(name, "WARN", f"route live but requires parameters: HTTP 422 · {detail_text(payload)}", started)
    else:
        record(name, "FAIL", f"HTTP {status} · {detail_text(payload)}", started)


def scan_frontend_contract() -> None:
    started = time.monotonic()
    source = CURRENT / "components/support-chat-widget-v2.tsx"
    if source.is_file():
        text = source.read_text(encoding="utf-8", errors="ignore")
        if 'if(!API_BASE)throw new Error("NEXT_PUBLIC_API_BASE is not configured")' in text:
            record(
                "frontend.same_origin_contract",
                "FAIL",
                "support chat rejects the portable same-origin API mode",
                started,
            )
            return
    api_file = CURRENT / "lib/api.ts"
    if api_file.is_file():
        text = api_file.read_text(encoding="utf-8", errors="ignore")
        if "browserOrigin" in text and "!configuredApiBase" in text:
            record("frontend.same_origin_contract", "PASS", "portable browser origin fallback present", started)
            return
    record("frontend.same_origin_contract", "WARN", "same-origin contract could not be proven from installed source", started)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only TwinPanel installed feature audit")
    parser.add_argument("--json", action="store_true", help="print JSON result only")
    args = parser.parse_args()

    api_port = int(os.getenv("TWINPANEL_API_PORT", "8095") or "8095")
    web_port = int(os.getenv("TWINPANEL_WEB_PORT", "3000") or "3000")
    api_base = f"http://127.0.0.1:{api_port}"
    web_base = f"http://127.0.0.1:{web_port}"

    started = time.monotonic()
    if CURRENT.is_symlink() and (CURRENT / "VERSION").is_file():
        record("install.active_release", "PASS", f"{CURRENT.resolve()} · {(CURRENT / 'VERSION').read_text().strip()}", started)
    else:
        record("install.active_release", "FAIL", "/opt/twinpanel/current is not a valid release symlink", started)

    for unit in ("twinpanel-api.service", "twinpanel-web.service", "nginx.service"):
        started = time.monotonic()
        state = unit_state(unit)
        record(f"service.{unit.removesuffix('.service')}", "PASS" if state == "active" else "FAIL", state, started)

    # Database/cache service names differ across Ubuntu/package/container installs.
    for label, choices in (
        ("postgresql", ("postgresql.service",)),
        ("redis", ("redis-server.service", "redis.service")),
    ):
        started = time.monotonic()
        states = [(unit, unit_state(unit)) for unit in choices]
        active = next((unit for unit, state in states if state == "active"), None)
        if active:
            record(f"service.{label}", "PASS", active, started)
        else:
            record(f"service.{label}", "WARN", ", ".join(f"{u}={s}" for u, s in states), started)

    for name, url in (
        ("health.api", f"{api_base}/health"),
        ("health.web", f"{web_base}/health"),
        ("health.nginx", "http://127.0.0.1/health"),
    ):
        started = time.monotonic()
        status, payload, _ = request_json(url)
        ok = status == 200 and isinstance(payload, dict) and payload.get("ok") is True
        record(name, "PASS" if ok else "FAIL", f"HTTP {status} · {detail_text(payload)}", started)

    scan_frontend_contract()

    token, token_detail = make_admin_token()
    if not token:
        record("auth.local_admin_token", "FAIL", token_detail)
    else:
        record("auth.local_admin_token", "PASS", token_detail)

    paths = openapi_paths(api_base)
    if paths:
        record("api.openapi", "PASS", f"{len(paths)} paths loaded")
    else:
        record("api.openapi", "FAIL", "OpenAPI route inventory unavailable")

    if token:
        started = time.monotonic()
        status, payload, headers = request_json("http://127.0.0.1/v1/auth/me", token=token)
        proxy_header = headers.get("x-twinpanel-proxy", "nginx-direct")
        record(
            "proxy.same_origin_admin",
            "PASS" if status == 200 else "FAIL",
            f"HTTP {status} · {proxy_header} · {detail_text(payload)}",
            started,
        )

        # Safe, read-only feature probes. Each one must exist in OpenAPI and
        # answer with the locally generated active-admin token.
        features = [
            ("feature.auth", "/v1/auth/me"),
            ("feature.dashboard", "/v1/admin/dashboard-summary"),
            ("feature.users", "/v1/admin/users-page"),
            ("feature.plans", "/v1/plans"),
            ("feature.subscriptions", "/v1/subscriptions"),
            ("feature.nodes", "/v1/nodes"),
            ("feature.tunnels", "/v1/tunnels"),
            ("feature.protocols", "/v1/admin/core-protocols"),
            ("feature.security", "/v1/admin/security/overview"),
            ("feature.payments", "/v1/payments/admin/intents"),
            ("feature.payment_settings", "/v1/payments/admin/settings"),
            ("feature.wallet", "/v1/admin/wallet"),
            ("feature.storefront", "/v1/storefront/settings"),
            ("feature.store_orders", "/v1/store/orders/admin"),
            ("feature.discounts", "/v1/discounts/admin"),
            ("feature.support", "/v1/admin/support/tickets"),
            ("feature.notifications", "/v1/admin/panel-notifications"),
            ("feature.backups", "/v1/admin/backups"),
            ("feature.domains", "/v1/admin/domains"),
            ("feature.general_settings", "/v1/settings/general"),
            ("feature.branding", "/v1/settings/branding"),
            ("feature.vpn_settings", "/v1/settings/vpn"),
            ("feature.telegram", "/v1/admin/telegram-bot"),
            ("feature.resellers", "/v1/admin/resellers"),
            ("feature.quota", "/v1/quota/health"),
            ("feature.update_system", "/v1/admin/system/release/status"),
        ]
        for name, path in features:
            safe_get_feature(name, path, api_base, token, paths)

    counts = {status: sum(1 for row in RESULTS if row.status == status) for status in ("PASS", "WARN", "FAIL")}
    payload = {
        "product": "TwinPanel",
        "mode": "installed-read-only",
        "version": (CURRENT / "VERSION").read_text().strip() if (CURRENT / "VERSION").is_file() else "unknown",
        "summary": counts,
        "results": [asdict(row) for row in RESULTS],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("=" * 88)
        print(f" TwinPanel Installed Feature Audit · {payload['version']}")
        print(" READ ONLY · no database mutations · no service changes")
        print("=" * 88)
        for row in RESULTS:
            marker = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[row.status]
            print(f"{marker:<7} {row.name:<34} {row.detail} ({row.elapsed_ms}ms)")
        print("=" * 88)
        print(f" PASS={counts['PASS']}  WARN={counts['WARN']}  FAIL={counts['FAIL']}")
        print("=" * 88)

    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
