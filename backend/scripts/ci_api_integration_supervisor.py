#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

import uvicorn


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app


BASE_URL = "http://127.0.0.1:8095"
REQUIRED_ROUTES = (
    "/v1/runtime/endpoints",
    "/v1/auth/login",
    "/v1/auth/me",
    "/v1/admin/users",
    "/v1/plans",
    "/v1/nodes",
    "/v1/tunnels",
    "/v1/subscriptions",
    "/v1/reseller/plans",
    "/v1/reseller/subscriptions/create",
    "/v1/reseller/traffic/buy",
    "/v1/reseller/bot-commerce/orders/{order_id}/approve",
    "/v1/tunnels/register",
    "/v1/tunnels/create-managed",
    "/v1/tunnels/{tunnel_id}/transports",
    "/v1/tunnels/{tunnel_id}/transport-mode",
    "/v1/tunnels/{tunnel_id}/mtunnel/install",
    "/v1/tunnels/{tunnel_id}/backhaul/install",
    "/v1/tunnels/{tunnel_id}/ssh/install",
    "/v1/payments/methods",
    "/v1/payments/intents",
    "/v1/payments/intents/{intent_id}/receipt-upload",
    "/v1/payments/admin/crypto-discount",
    "/v1/wallet/methods",
    "/v1/wallet/topups",
    "/v1/wallet/topups/{topup_id}/submit",
    "/v1/admin/wallet/wallets",
    "/v1/admin/wallet/topups",
    "/v1/admin/wallet/topups/{topup_id}/approve",
    "/v1/admin/telegram-bot",
    "/v1/admin/telegram-bot/test",
    "/v1/settings/vpn/outbound-performance/{node_id}/{tag}/advanced-test",
    "/v1/settings/vpn/outbound-performance/{node_id}/tuning",
    "/v1/settings/vpn/outbound-performance/{node_id}/tuning/apply",
    "/v1/settings/vpn/outbound-performance/{node_id}/tuning/rollback",
    "/v1/settings/vpn/outbound-performance/{node_id}/advanced-state",
)
REQUIRED_ROUTE_PREFIXES = (
    "/v1/xray-modern",
    "/v1/xray-modern-admin",
)
SMOKE_COMMANDS = (
    (sys.executable, "-m", "scripts.tunnel_managed_smoke"),
    (sys.executable, "-m", "scripts.managed_relay_recovery_v20_smoke"),
    (sys.executable, "-m", "scripts.public_direct_tuning_v19_smoke"),
    (sys.executable, "-m", "scripts.transport_policy_v16_smoke"),
    (sys.executable, "tests/spoof_health_guard_v211_smoke.py"),
    (sys.executable, "tests/outbound_performance_v261_smoke.py"),
    (sys.executable, "tests/outbound_performance_v262_smoke.py"),
    (sys.executable, "scripts/api_core_smoke.py"),
)
SERVER_ERRORS: list[str] = []


def _get_json(path: str, timeout: float = 3.0) -> dict:
    request = urllib.request.Request(BASE_URL + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _serve(server: uvicorn.Server) -> None:
    try:
        server.run()
    except BaseException:
        SERVER_ERRORS.append(traceback.format_exc())


def _wait_for_ready(server: uvicorn.Server, server_thread: threading.Thread, *, timeout_seconds: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_error = "not attempted"
    while time.monotonic() < deadline:
        if not server_thread.is_alive():
            details = SERVER_ERRORS[-1] if SERVER_ERRORS else "no Python exception captured"
            raise RuntimeError(
                "uvicorn server thread exited before readiness; "
                f"started={server.started} should_exit={server.should_exit} force_exit={server.force_exit}\n"
                + details
            )
        try:
            payload = _get_json("/health/ready")
            if payload.get("ok") is True:
                return payload
            last_error = f"unexpected readiness payload: {payload!r}"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = repr(exc)
        time.sleep(0.5)
    raise RuntimeError(f"API did not become ready: {last_error}")


def _verify_routes() -> None:
    schema = _get_json("/openapi.json", timeout=10.0)
    paths = set((schema.get("paths") or {}).keys())
    missing = [route for route in REQUIRED_ROUTES if route not in paths]
    missing_prefixes = [
        prefix for prefix in REQUIRED_ROUTE_PREFIXES if not any(path.startswith(prefix) for path in paths)
    ]
    if missing or missing_prefixes:
        raise RuntimeError(
            "required API routes missing: "
            + json.dumps(
                {"exact": missing, "prefixes": missing_prefixes},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    print(f"API_ROUTE_VERIFY_OK exact={len(REQUIRED_ROUTES)} prefixes={len(REQUIRED_ROUTE_PREFIXES)}")


def _run_smokes() -> None:
    smoke_env = os.environ.copy()
    existing_pythonpath = smoke_env.get("PYTHONPATH", "").strip()
    backend_path = str(BACKEND_DIR)
    smoke_env["PYTHONPATH"] = (
        backend_path if not existing_pythonpath else f"{backend_path}{os.pathsep}{existing_pythonpath}"
    )
    for command in SMOKE_COMMANDS:
        print("API_SMOKE_RUN", " ".join(command), flush=True)
        subprocess.run(command, cwd=BACKEND_DIR, check=True, env=smoke_env)


if __name__ == "__main__":
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=8095,
        loop="asyncio",
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server_thread = threading.Thread(
        target=_serve,
        args=(server,),
        name="twinpanel-ci-api",
        daemon=False,
    )
    server_thread.start()

    try:
        ready = _wait_for_ready(server, server_thread)
        checks = ready.get("checks") or {}
        if checks.get("database") is not True or checks.get("redis") is not True:
            raise RuntimeError(f"readiness dependency check failed: {ready!r}")
        print("API_READINESS_OK", json.dumps(ready, ensure_ascii=False, sort_keys=True))
        _verify_routes()
        _run_smokes()
        print("API_INTEGRATION_SMOKE_OK")
    finally:
        server.should_exit = True
        server_thread.join(timeout=15.0)
        if server_thread.is_alive():
            server.force_exit = True
            server_thread.join(timeout=5.0)
        if server_thread.is_alive():
            raise RuntimeError("uvicorn server thread did not stop cleanly")
