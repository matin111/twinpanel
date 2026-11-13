"""Regression guards for adaptive controller-side central-family staging.

This deliberately exercises only scheduling decisions; no VPN service,
database mutation or user credentials are involved.
"""
from __future__ import annotations

from app.services.central_node_runtime_engine_v1 import runtime_family_concurrency


def test_small_controller_stays_serial(monkeypatch):
    monkeypatch.delenv("TWINPANEL_CENTRAL_FAMILY_CONCURRENCY", raising=False)
    assert runtime_family_concurrency(cores=2, load=0.0) == 1
    assert runtime_family_concurrency(cores=4, load=1.0) == 1


def test_busy_large_controller_stays_serial(monkeypatch):
    monkeypatch.delenv("TWINPANEL_CENTRAL_FAMILY_CONCURRENCY", raising=False)
    assert runtime_family_concurrency(cores=16, load=7.0) == 1
    assert runtime_family_concurrency(cores=8, load=3.0) == 1


def test_idle_large_controller_keeps_fast_parallelism(monkeypatch):
    monkeypatch.delenv("TWINPANEL_CENTRAL_FAMILY_CONCURRENCY", raising=False)
    assert runtime_family_concurrency(cores=16, load=2.0) == 2
    assert runtime_family_concurrency(cores=8, load=1.0) == 2


def test_valid_explicit_override(monkeypatch):
    monkeypatch.setenv("TWINPANEL_CENTRAL_FAMILY_CONCURRENCY", "1")
    assert runtime_family_concurrency(cores=16, load=0.0) == 1
    monkeypatch.setenv("TWINPANEL_CENTRAL_FAMILY_CONCURRENCY", "3")
    assert runtime_family_concurrency(cores=16, load=99.0) == 3


def test_invalid_override_fails_back_to_adaptive(monkeypatch):
    monkeypatch.setenv("TWINPANEL_CENTRAL_FAMILY_CONCURRENCY", "invalid")
    assert runtime_family_concurrency(cores=16, load=7.0) == 1
    monkeypatch.setenv("TWINPANEL_CENTRAL_FAMILY_CONCURRENCY", "99")
    assert runtime_family_concurrency(cores=16, load=1.0) == 2
