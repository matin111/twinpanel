#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


BASE = str(os.getenv("TWINPANEL_SMOKE_BASE", "http://127.0.0.1:8095")).rstrip("/")
ADMIN_EMAIL = os.environ["TWINPANEL_ADMIN_EMAIL"]
ADMIN_PASSWORD = os.environ["TWINPANEL_ADMIN_PASSWORD"]


def request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    headers = {"Accept": "application/json"}
    data = None

    if token:
        headers["Authorization"] = f"Bearer {token}"

    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read().decode("utf-8")
            if not raw:
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"{method} {path} -> HTTP {exc.code}: {body[:1600]}"
        ) from exc


def request_error(
    method: str,
    path: str,
    *,
    expected_status: int,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    headers = {"Accept": "application/json"}
    data = None

    if token:
        headers["Authorization"] = f"Bearer {token}"

    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code != expected_status:
            raise RuntimeError(
                f"{method} {path} -> HTTP {exc.code}, expected {expected_status}: {body[:1600]}"
            ) from exc
        return json.loads(body) if body else None

    raise RuntimeError(
        f"{method} {path} unexpectedly succeeded; expected HTTP {expected_status}"
    )


def main() -> int:
    ready = request("GET", "/health/ready")
    assert ready["ok"] is True, ready
    assert ready["checks"]["database"] is True, ready
    assert ready["checks"]["redis"] is True, ready

    runtime = request("GET", "/v1/runtime/endpoints")
    api_base = str(runtime.get("api_base") or "")
    assert api_base, runtime
    assert "movilineapp.com" not in api_base.lower(), runtime

    login = request(
        "POST",
        "/v1/auth/login",
        payload={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD,
        },
    )
    token = login.get("access_token")
    assert token, login

    me = request("GET", "/v1/auth/me", token=token)
    assert me["email"] == ADMIN_EMAIL, me
    assert me["role"] == "admin", me

    stats = request("GET", "/v1/admin/stats", token=token)
    assert isinstance(stats.get("users"), int), stats

    user = request(
        "POST",
        "/v1/admin/users",
        token=token,
        payload={
            "email": "customer-smoke@example.com",
            "password": "Customer-Smoke-2026!",
            "full_name": "API Smoke Customer",
        },
    )
    user_id = int(user["id"])

    plan = request(
        "POST",
        "/v1/plans",
        token=token,
        payload={
            "name": "API Smoke Plan",
            "description": "CI-only standalone API validation",
            "duration_days": 30,
            "traffic_gb": 20,
            "device_limit": 2,
            "price_toman": 100000,
            "enable_cisco": True,
            "enable_openvpn": True,
            "enable_wireguard": True,
            "enable_l2tp": True,
            "enable_v2ray": True,
        },
    )
    plan_id = int(plan["id"])

    iran = request(
        "POST",
        "/v1/nodes",
        token=token,
        payload={
            "name": "api-smoke-iran",
            "node_type": "iran",
            "country_code": "IR",
            "public_ip": "198.51.100.10",
            "capacity_users": 100,
        },
    )
    iran_id = int(iran["id"])

    exit_node = request(
        "POST",
        "/v1/nodes",
        token=token,
        payload={
            "name": "api-smoke-exit",
            "node_type": "exit",
            "country_code": "DE",
            "public_ip": "198.51.100.20",
            "capacity_users": 100,
        },
    )
    exit_id = int(exit_node["id"])

    tunnel = request(
        "POST",
        "/v1/tunnels/register",
        token=token,
        payload={
            "iran_node_id": iran_id,
            "exit_node_id": exit_id,
            "transport": "ssh_tun",
            "priority": 100,
            "is_active": True,
        },
    )
    tunnel_id = int(tunnel["id"])

    transports = request(
        "GET",
        f"/v1/tunnels/{tunnel_id}/transports",
        token=token,
    )
    names = {
        str(item["transport"])
        for item in transports.get("transports", [])
    }
    assert names == {"mtunnel", "backhaul", "ssh_tun"}, transports

    # This generic API smoke intentionally creates DB-only placeholder nodes with
    # documentation IPs and no protocol runtime/SSH access. V2 creation must now
    # fail closed instead of reporting a false ACTIVE subscription. The dedicated
    # subscription-creation workflow covers the successful provisioned path.
    failed_create = request_error(
        "POST",
        "/v1/subscriptions/admin-create-v2",
        expected_status=502,
        token=token,
        payload={
            "user_id": user_id,
            "plan_id": plan_id,
            "node_ids": [iran_id, exit_id],
            "protocols": [
                "cisco",
                "openvpn",
                "wireguard",
                "l2tp",
                "v2ray",
            ],
        },
    )
    detail = failed_create.get("detail") or {}
    assert "Provisioning" in str(detail.get("message") or ""), failed_create
    subscription_id = int(detail["subscription_id"])

    subscriptions_v2 = request(
        "GET",
        "/v1/subscriptions/admin-list-v2",
        token=token,
    )
    listed = next(
        (
            item
            for item in subscriptions_v2
            if int(item["id"]) == subscription_id
        ),
        None,
    )
    assert listed is not None, subscriptions_v2
    assert listed["status"] == "suspended", listed
    assert set(listed["node_ids"]) >= {iran_id, exit_id}, listed
    assert set(listed["protocols"]) == {
        "cisco",
        "openvpn",
        "wireguard",
        "l2tp",
        "v2ray",
    }, listed
    assert round(float(listed["traffic_limit_gb"]), 2) == 20.0, listed
    assert int(listed["activation_duration_days"]) == 30, listed
    assert int(listed["device_limit"]) == 2, listed
    assert listed["device_limit_source"] == "subscription", listed
    assert listed["traffic_unlimited"] is False, listed
    assert listed["duration_unlimited"] is False, listed

    # Keep the legacy endpoint available for older customers/upgrades and ensure
    # the failed V2 desired-state remains auditable rather than disappearing.
    subscriptions = request("GET", "/v1/subscriptions", token=token)
    assert any(int(item["id"]) == subscription_id for item in subscriptions), subscriptions

    print(
        "API_CORE_SMOKE_OK",
        f"user={user_id}",
        f"plan={plan_id}",
        f"iran={iran_id}",
        f"exit={exit_id}",
        f"tunnel={tunnel_id}",
        f"subscription={subscription_id}",
        "subscription_create=fail_closed_without_runtime",
        f"api_base={api_base}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
