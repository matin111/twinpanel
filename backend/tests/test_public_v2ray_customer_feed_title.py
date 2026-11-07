"""Customer-facing V2Ray subscription titles must never use the TwinPanel brand."""
from types import SimpleNamespace

from app.routers import public_connection_multilink_v7 as v7
from app.routers.public_connection_all_multilink_v34 import _headers


def test_v2ray_direct_feed_uses_own_subscription_username(monkeypatch):
    sub = SimpleNamespace(id=3848, account_username="named_customer")
    monkeypatch.setattr(v7, "_subscription_content", lambda token, db: ("encoded", 4, 5))
    monkeypatch.setattr(v7.account_delivery, "_subscription_from_share_token", lambda token, db: sub)
    result = v7._subscription_response("opaque", object())
    assert result.headers["Profile-Title"] == "named_customer-v2ray"
    assert result.headers["Profile-Title"] != "TwinPanel-V2Ray"
    assert result.body == b"encoded"


def test_v2ray_direct_and_multilink_titles_match(monkeypatch):
    sub = SimpleNamespace(id=3848, account_username="named_customer")
    monkeypatch.setattr(v7, "_subscription_content", lambda token, db: ("encoded", 4, 5))
    monkeypatch.setattr(v7.account_delivery, "_subscription_from_share_token", lambda token, db: sub)
    direct = v7._subscription_response("opaque", object())
    multi = _headers(sub, "v2ray", "uri", 5)
    assert direct.headers["Profile-Title"] == multi["Profile-Title"]


def test_missing_username_has_safe_nonbrand_fallback(monkeypatch):
    sub = SimpleNamespace(id=99, account_username=None)
    monkeypatch.setattr(v7, "_subscription_content", lambda token, db: ("encoded", 1, 1))
    monkeypatch.setattr(v7.account_delivery, "_subscription_from_share_token", lambda token, db: sub)
    result = v7._subscription_response("opaque", object())
    assert result.headers["Profile-Title"] == "user-99-v2ray"
