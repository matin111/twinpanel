from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from app import system_release as licensing


def test_global_outage_falls_back_to_iran(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWINPANEL_LICENSE_API_URL", "https://license-global.example")
    monkeypatch.setenv("TWINPANEL_LICENSE_IR_API_URL", "https://license-ir.example")
    calls: list[str] = []

    def fake_post(url: str, **kwargs):
        calls.append(url)
        request = httpx.Request("POST", url)
        if "license-global" in url:
            raise httpx.ConnectError("global unavailable", request=request)
        return httpx.Response(200, request=request, json={"status": "licensed"})

    monkeypatch.setattr(licensing.httpx, "post", fake_post)
    payload = licensing._vendor_post("/v1/license/validate", {"installation_id": "test"})

    assert payload["status"] == "licensed"
    assert payload["_validation_source"] == "iran"
    assert len(calls) == 2


def test_authoritative_4xx_never_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWINPANEL_LICENSE_API_URL", "https://license-global.example")
    monkeypatch.setenv("TWINPANEL_LICENSE_IR_API_URL", "https://license-ir.example")
    calls: list[str] = []

    def fake_post(url: str, **kwargs):
        calls.append(url)
        request = httpx.Request("POST", url)
        return httpx.Response(403, request=request, json={"detail": "revoked"})

    monkeypatch.setattr(licensing.httpx, "post", fake_post)
    with pytest.raises(httpx.HTTPStatusError):
        licensing._vendor_post("/v1/license/validate", {})

    assert calls == ["https://license-global.example/v1/license/validate"]


def test_verified_cache_is_used_only_inside_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWINPANEL_LICENSE_OFFLINE_GRACE_SECONDS", "2592000")
    monkeypatch.setattr(
        licensing,
        "_verify_entitlement",
        lambda token: {"status": "licensed", "installation_id": "test"},
    )
    cached = {
        "status": "licensed",
        "signed_entitlement": "signed-token",
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": "2099-01-01T00:00:00+00:00",
    }

    state = licensing._verified_offline_state(cached, httpx.ConnectError("offline"))

    assert state["validation"] == "offline_cache"
    assert state["validation_source"] == "offline_cache"
    assert state["offline_mode"] is True
    assert state["offline_grace_seconds_remaining"] > 0


def test_cached_revocation_stays_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        licensing,
        "_verify_entitlement",
        lambda token: {"status": "revoked", "installation_id": "test"},
    )
    cached = {
        "status": "revoked",
        "signed_entitlement": "signed-revoked-token",
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }

    state = licensing._verified_offline_state(cached, httpx.ConnectError("offline"))

    assert state["status"] == "revoked"
    assert state["offline_grace_seconds_remaining"] == 0
