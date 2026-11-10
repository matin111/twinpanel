"""Regression checks for staged Exit publication without touching a server or DB."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models import NodeType
from app.protocol_account_registry import ALL_PROTOCOL_KEYS
from app.routers.provision import InstallIn
from app.routers.publish_node_all_users_v1 import BackgroundNodeInstallIn
from app.services.new_node_readiness_v1 import verify_new_exit_readiness
from app.services.node_stage_publish_guard_v1 import require_staged_node_publish_ready


class _Rows:
    def __init__(self, result):
        self.result = result

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self.result

    def all(self):
        return self.result


class _Db:
    def __init__(self, job=None, node=None, configs=()):
        self.job = job
        self.node = node
        self.configs = list(configs)

    def query(self, *args, **kwargs):
        return _Rows(self.job if self.node is None else self.configs)

    def get(self, *args, **kwargs):
        return self.node


@pytest.mark.parametrize("stage", ["queued", "installing_base", "installing_modern", "failed"])
def test_staged_node_cannot_be_manually_published_before_readiness(stage):
    db = _Db(job=SimpleNamespace(stage=stage))
    with pytest.raises(HTTPException) as err:
        require_staged_node_publish_ready(db, 14)
    assert err.value.status_code == 409


@pytest.mark.parametrize("stage", ["verified_ready", "users_queued", "completed"])
def test_staged_node_allows_publish_after_health_validation(stage):
    require_staged_node_publish_ready(_Db(job=SimpleNamespace(stage=stage, installed_protocols=16)), 14)


def test_partial_exit_rejects_unsafe_legacy_bulk_publish():
    db = _Db(job=SimpleNamespace(stage="completed", installed_protocols=15))
    with pytest.raises(HTTPException) as err:
        require_staged_node_publish_ready(db, 27)
    assert err.value.status_code == 409
    assert err.value.detail == "PARTIAL_NODE_REQUIRES_CENTRAL_ADMISSION"


def test_existing_nonstaged_node_retains_legacy_manual_control():
    require_staged_node_publish_ready(_Db(job=None), 1)


def test_background_exit_installs_classic_family_by_default():
    args = dict(host="127.0.0.1", password="not-real", name="test", node_type=NodeType.EXIT)
    payload = BackgroundNodeInstallIn(**args)
    assert all((
        payload.install_cisco,
        payload.install_openvpn,
        payload.install_wireguard,
        payload.install_l2tp,
    ))
    assert payload.publish_to_all_users is False

    # The existing direct/manual installer remains opt-out compatible.
    direct = InstallIn(**args)
    assert direct.defer_subscription_sync is False


def test_readiness_denies_twelve_protocol_node_without_ssh():
    node = SimpleNamespace(node_type=NodeType.EXIT, retired_at=None)
    configs = [
        SimpleNamespace(protocol=key, status="online", port=8443)
        for key in ALL_PROTOCOL_KEYS
        if key not in {"cisco", "openvpn", "wireguard", "l2tp"}
    ]
    result = asyncio.run(verify_new_exit_readiness(_Db(node=node, configs=configs), 14))
    assert result["ok"] is False
    assert result["ready_count"] == 12
    assert set(result["missing"]) == {"cisco", "openvpn", "wireguard", "l2tp"}
