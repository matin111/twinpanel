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

    # V2 is the admin-panel contract. Deliberately omit traffic, duration and
    # device limit so the API itself must apply the selected plan defaults.
    subscription = request(
        "POST",
        "/v1/subscriptions/admin-create-v2",
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
    subscription_id = int(subscription["id"])
    assert subscription["status"] == "active", subscription
    assert set(subscription["node_ids"]) >= {iran_id, exit_id}, subscription
    assert set(subscription["protocols"]) == {
        "cisco",
        "openvpn",
        "wireguard",
        "l2tp",
        "v2ray",
    }, subscription
    assert round(float(subscription["traffic_limit_gb"]), 2) == 20.0, subscription
    assert int(subscription["activation_duration_days"]) == 30, subscription
    assert int(subscription["device_limit"]) == 2, subscription
    assert subscription["device_limit_source"] == "subscription", subscription
    assert subscription["traffic_unlimited"] is False, subscription
    assert subscription["duration_unlimited"] is False, subscription

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
    assert int(listed["device_limit"]) == 2, listed
    assert int(listed["activation_duration_days"]) == 30, listed

    # Keep the legacy endpoint available for older customers/upgrades.
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
        f"api_base={api_base}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
