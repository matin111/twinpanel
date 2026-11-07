"""New Exit must install all 16 and validate real runtime before user fanout."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeProtocolConfig, NodeType, NodeStatus
from app.modern_protocol_models import ModernProtocolSetting
from app.protocol_account_registry import ALL_PROTOCOL_KEYS, CLASSIC_PROTOCOL_KEYS, MODERN_PROTOCOL_KEYS
from app.protocol_catalog import PROTOCOL_CATALOG
from app.services.new_node_modern_bootstrap_v1 import build_modern_bootstrap_plan
from app.services import new_node_readiness_v1 as readiness

ROOT = Path(__file__).resolve().parents[1]


def test_all_sixteen_catalog_runtime_keys_active_after_standalone_import():
    assert len(ALL_PROTOCOL_KEYS) == len(set(ALL_PROTOCOL_KEYS)) == 16
    assert len(CLASSIC_PROTOCOL_KEYS) == 5
    assert len(MODERN_PROTOCOL_KEYS) == 11
    assert all(PROTOCOL_CATALOG[key]["runtime_status"] == "ready"
               for key in MODERN_PROTOCOL_KEYS)


def test_first_exit_builds_full_modern_plan_without_template():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[
        Node.__table__, NodeProtocolConfig.__table__,
        ModernProtocolSetting.__table__,
    ])
    try:
        with Session(engine) as db:
            db.add(Node(
                id=77, name="First Exit", node_type=NodeType.EXIT,
                country_code="DE", public_ip="192.0.2.77",
                agent_url="https://192.0.2.77:9443",
                status=NodeStatus.OFFLINE, show_to_users=False,
            ))
            db.commit()
            plan = build_modern_bootstrap_plan(db, 77)
            assert set(plan["protocols"]) == set(MODERN_PROTOCOL_KEYS)
            assert plan["skipped_no_template"] == []
            assert plan["skipped_port_conflict"] == []
            assert len(set(plan["ports"].values())) == 11
            assert all(plan["sources"][key]["mode"] == "catalog_default"
                       for key in MODERN_PROTOCOL_KEYS)
            assert all(plan["sources"][key]["node_id"] is None
                       for key in MODERN_PROTOCOL_KEYS)
    finally:
        engine.dispose()


class _ReadyDB:
    def __init__(self, status_override=None):
        self.status_override = status_override or {}
    def get(self, _model, _node_id):
        return SimpleNamespace(
            node_type=NodeType.EXIT, retired_at=None,
        )
    def query(self, _model):
        return self
    def filter(self, *_clauses):
        return self
    def all(self):
        return [
            SimpleNamespace(
                protocol=key, status=self.status_override.get(key, "online"),
                port=15000 + i,
            )
            for i, key in enumerate(ALL_PROTOCOL_KEYS)
        ]


def test_one_readonly_connection_checks_five_classic_and_eleven_modern():
    conn = SimpleNamespace(
        close=lambda: None,
        wait_closed=AsyncMock(return_value=None),
    )
    with (
        patch.object(readiness, "connect_protocol_runtime",
                     new_callable=AsyncMock, return_value=conn) as connect,
        patch.object(readiness, "_protocol_live_health",
                     new_callable=AsyncMock, return_value={"ok": True}) as classic,
        patch.object(readiness, "profile_health",
                     new_callable=AsyncMock, return_value={"ok": True}) as modern,
    ):
        result = asyncio.run(readiness.verify_new_exit_readiness(_ReadyDB(), 77))
        assert result["ok"] is True
        assert result["ready_count"] == result["required_count"] == 16
        assert result["missing"] == []
        assert connect.await_count == 1
        assert classic.await_count == 5
        assert modern.await_count == 11
        assert conn.wait_closed.await_count == 1


def test_missing_protocol_denies_enrollment_without_connecting():
    with patch.object(readiness, "connect_protocol_runtime",
                      new_callable=AsyncMock) as connect:
        result = asyncio.run(readiness.verify_new_exit_readiness(
            _ReadyDB({"sudoku": "error"}), 77,
        ))
        assert result["ok"] is False
        assert result["missing"] == ["sudoku"]
        assert result["reason"] == "protocol_not_installed"
        connect.assert_not_awaited()


def test_live_listener_failure_blocks_publish():
    conn = SimpleNamespace(
        close=lambda: None,
        wait_closed=AsyncMock(return_value=None),
    )
    async def probe(_conn, protocol, _port):
        return {"ok": protocol != "amneziawg"}
    with (
        patch.object(readiness, "connect_protocol_runtime",
                     new_callable=AsyncMock, return_value=conn),
        patch.object(readiness, "_protocol_live_health",
                     new_callable=AsyncMock, return_value={"ok": True}),
        patch.object(readiness, "profile_health", side_effect=probe),
    ):
        result = asyncio.run(readiness.verify_new_exit_readiness(_ReadyDB(), 77))
        assert result["ok"] is False
        assert result["reason"] == "live_health_failed"
        assert result["missing"] == ["amneziawg"]
        assert result["ready_count"] == 15


def test_install_sequence_and_guard_not_fake_progress():
    src = (ROOT / "app/routers/publish_node_all_users_v1.py").read_text()
    block = src.split("async def _install_node_in_background(", 1)[1].split(
        '@router.post("/install-background-v1"', 1
    )[0]
    assert "defer_subscription_sync=payload.node_type == NodeType.EXIT" in block
    assert block.index("await install_node(") < block.index(
        "await ensure_classic_protocol("
    ) < block.index("await bootstrap_new_exit_modern_protocols("
    ) < block.index("await verify_new_exit_readiness("
    ) < block.index("await publish_node_to_all_users(")
    assert block.index("if not ready:") < block.index(
        "await publish_node_to_all_users("
    )
    assert 'error_code="PROTOCOL_SETUP_INCOMPLETE"' in block

    prov = (ROOT / "app/routers/provision.py").read_text()
    assert "defer_subscription_sync: bool = False" in prov
    assert "show_to_users=(payload.node_type != NodeType.EXIT or not payload.defer_subscription_sync)" in prov
    assert 'if payload.defer_subscription_sync:' in prov

    ui = (ROOT.parent / "components/node-add-modal-bridge.tsx").read_text()
    assert "const EXIT_PROTOCOLS={install_cisco:true" in ui
    assert "install_openvpn:true" in ui
    assert "install_wireguard:true" in ui
    assert "install_l2tp:true" in ui
    assert "install_v2ray:false" in ui
    assert "const [publishToAll,setPublishToAll]=useState(true)" in ui


def test_remapped_ports_are_used_for_delivered_node_links():
    src = (ROOT / "app/routers/modern_protocol_admin_v3.py").read_text()
    assert 'remaps = (result.get("core") or {}).get("port_remaps") or {}' in src
    assert 'applied_port = int(remap.get("to") or health.get("port") or requested_port)' in src
    assert '_save_setting(db, node.id, key, preset, effective, applied_port)' in src
