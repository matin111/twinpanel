from __future__ import annotations

from types import SimpleNamespace

from app.domain_models import DomainType
from app.services import public_urls


class _DB:
    pass


def _install_origins(monkeypatch, values: dict[DomainType, str | None]):
    monkeypatch.setattr(
        public_urls,
        "_domain_origin",
        lambda _db, kind: values.get(kind),
    )


def _settings(subscription: str = "", api: str = ""):
    return SimpleNamespace(
        public_subscription_base_url=subscription,
        public_api_fallback=api,
    )


def test_subscription_domain_remains_strongest_authority(monkeypatch):
    _install_origins(
        monkeypatch,
        {
            DomainType.SUBSCRIPTION: "https://managed.example.com",
            DomainType.SHOP: "https://shop.example.com",
        },
    )
    monkeypatch.setattr(
        public_urls,
        "settings",
        _settings(
            subscription="https://edge.example.com",
            api="http://198.51.100.10",
        ),
    )
    monkeypatch.setattr(
        public_urls,
        "request_origin",
        lambda _request: "https://request.example.com",
    )

    assert (
        public_urls.subscription_base_url(_DB(), object())
        == "https://managed.example.com"
    )


def test_explicit_subscription_origin_beats_request_and_api_fallback(monkeypatch):
    _install_origins(monkeypatch, {})
    monkeypatch.setattr(
        public_urls,
        "settings",
        _settings(
            subscription="  https://connect.example.com/  ",
            api="http://198.51.100.10",
        ),
    )
    monkeypatch.setattr(
        public_urls,
        "request_origin",
        lambda _request: "http://198.51.100.10",
    )

    assert (
        public_urls.subscription_base_url(_DB(), object())
        == "https://connect.example.com"
    )


def test_request_origin_is_used_when_no_dedicated_subscription_origin(monkeypatch):
    _install_origins(monkeypatch, {})
    monkeypatch.setattr(
        public_urls,
        "settings",
        _settings(api="http://198.51.100.10"),
    )
    monkeypatch.setattr(
        public_urls,
        "request_origin",
        lambda _request: "https://public.example.com",
    )

    assert (
        public_urls.subscription_base_url(_DB(), object())
        == "https://public.example.com"
    )


def test_other_service_domain_still_precedes_legacy_api_fallback(monkeypatch):
    _install_origins(
        monkeypatch,
        {DomainType.PANEL: "https://panel.example.com"},
    )
    monkeypatch.setattr(
        public_urls,
        "settings",
        _settings(api="http://198.51.100.10"),
    )
    monkeypatch.setattr(
        public_urls,
        "request_origin",
        lambda _request: None,
    )

    assert (
        public_urls.subscription_base_url(_DB())
        == "https://panel.example.com"
    )


def test_api_fallback_remains_last_subscription_compatibility_fallback(monkeypatch):
    _install_origins(monkeypatch, {})
    monkeypatch.setattr(
        public_urls,
        "settings",
        _settings(api="http://198.51.100.10/"),
    )
    monkeypatch.setattr(
        public_urls,
        "request_origin",
        lambda _request: None,
    )

    assert (
        public_urls.subscription_base_url(_DB())
        == "http://198.51.100.10"
    )


def test_api_base_url_contract_is_unchanged(monkeypatch):
    _install_origins(monkeypatch, {})
    monkeypatch.setattr(
        public_urls,
        "settings",
        _settings(
            subscription="https://connect.example.com",
            api="http://198.51.100.10/",
        ),
    )
    monkeypatch.setattr(
        public_urls,
        "request_origin",
        lambda _request: "https://request.example.com",
    )

    assert (
        public_urls.api_base_url(_DB(), object())
        == "http://198.51.100.10"
    )
