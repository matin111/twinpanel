"""New Exit: prepare all registered protocols before joining existing accounts.

No live SSH, credentials, nodes or installations used by these contracts.
"""
from __future__ import annotations

import ast
from pathlib import Path

from app.protocol_account_registry import ALL_PROTOCOL_KEYS, CLASSIC_PROTOCOL_KEYS, MODERN_PROTOCOL_KEYS
from app.protocol_catalog import PROTOCOL_CATALOG

ROOT = Path(__file__).resolve().parents[1]


def test_sixteen_protocols_are_single_registry():
    assert len(ALL_PROTOCOL_KEYS) == 16
    assert len(CLASSIC_PROTOCOL_KEYS) == 5
    assert len(MODERN_PROTOCOL_KEYS) == 11
    assert len(set(ALL_PROTOCOL_KEYS)) == len(ALL_PROTOCOL_KEYS)
    assert set(MODERN_PROTOCOL_KEYS) == set(PROTOCOL_CATALOG)


def test_unavailable_adapters_cannot_be_misreported_ready():
    pending = [key for key in MODERN_PROTOCOL_KEYS
               if PROTOCOL_CATALOG[key]["runtime_status"] != "ready"]
    # Dynamic contract: the bootstrap must not advertise a pending adapter.
    if pending:
        src = (ROOT / "app/services/new_node_modern_bootstrap_v1.py").read_text()
        assert 'definition.get("runtime_status") != "ready"' in src


def test_background_install_sequence_and_entitlement_delivery():
    src = (ROOT / "app/routers/publish_node_all_users_v1.py").read_text()
    ast.parse(src)
    body = src.split("async def _install_node_in_background(", 1)[1].split(
        '@router.post("/install-background-v1"', 1
    )[0]
    assert "defer_subscription_sync=payload.node_type == NodeType.EXIT" in body
    assert body.index("await install_node(") < body.index("await ensure_classic_protocol(")
    assert body.index("await ensure_classic_protocol(") < body.index(
        "await bootstrap_new_exit_modern_protocols("
    )
    assert body.index("await bootstrap_new_exit_modern_protocols(") < body.index(
        "missing = sorted(set(ALL_PROTOCOL_KEYS) - ready)"
    )
    assert body.index("missing = sorted(set(ALL_PROTOCOL_KEYS) - ready)") < body.index(
        "await publish_node_to_all_users_v2("
    )
    assert "if missing or not modern_bootstrap.get(\"ok\")" in body
    assert "node_id=node_id, db=db" in body
    assert "verify_new_exit_readiness(db, node_id)" in body
    assert body.index("await verify_new_exit_readiness(") < body.index(
        "await publish_node_to_all_users_v2("
    )
    assert "SubscriptionNode(" not in body
    assert "sync_installed_node_to_subscriptions" not in body
    assert "NodeProtocolConfig.status" not in body  # query real config rows


def test_deferred_install_does_not_run_legacy_subscription_loop():
    src = (ROOT / "app/routers/provision.py").read_text()
    ast.parse(src)
    assert "defer_subscription_sync: bool = False" in src
    assert "show_to_users=(payload.node_type != NodeType.EXIT or not payload.defer_subscription_sync)" in src
    tail = src.split("# TWINPANEL_INSTALL_THEN_AUTO_ENROLL_V1", 1)[1].split(
        "# TWINPANEL_MANUAL_IRAN_EXIT_TUNNEL_V2", 1
    )[0]
    assert "if not payload.defer_subscription_sync:" in tail
    assert tail.index("if not payload.defer_subscription_sync:") < tail.index(
        "await sync_installed_node_to_subscriptions("
    )


def test_add_node_defaults_to_auto_enroll_and_no_double_xray_install():
    ui = (ROOT.parent / "components/node-add-modal-bridge.tsx").read_text()
    assert "setPublishToAll]=useState(true)" in ui
    assert "install_cisco:true" in ui
    assert "install_openvpn:true" in ui
    assert "install_wireguard:true" in ui
    assert "install_l2tp:true" in ui
    assert "install_v2ray:false" in ui  # dedicated Xray bootstrap
    assert "publish_to_all_users:draft.node_type===\"exit\"?publishToAll:false" in ui



def test_first_exit_uses_11_catalog_defaults_not_missing_templates():
    """No other node must be needed to prepare a fresh 16-protocol Exit."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.models import Node, NodeProtocolConfig, NodeStatus, NodeType
    from app.modern_protocol_models import ModernProtocolSetting
    from app.services.new_node_modern_bootstrap_v1 import (
        build_modern_bootstrap_plan,
    )
    from app.protocol_catalog import resolve_settings

    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine, tables=[
            Node.__table__,
            NodeProtocolConfig.__table__,
            ModernProtocolSetting.__table__,
        ],
    )
    try:
        with Session(engine) as db:
            db.add(Node(
                id=123, name="Fresh Exit", node_type=NodeType.EXIT,
                public_ip="192.0.2.123",
                agent_url="https://192.0.2.123:9443",
                country_code="DE", status=NodeStatus.ONLINE,
            ))
            db.commit()
            plan = build_modern_bootstrap_plan(db, 123)
            assert set(plan["protocols"]) == set(MODERN_PROTOCOL_KEYS)
            assert plan["skipped_no_template"] == []
            assert plan["skipped_port_conflict"] == []
            assert len(set(plan["ports"].values())) == 11
            for key in MODERN_PROTOCOL_KEYS:
                assert plan["sources"][key]["mode"] == "catalog_default"
                assert plan["sources"][key]["node_id"] is None
                preset, _, _ = resolve_settings(key, "recommended", {})
                assert preset == "recommended"
    finally:
        engine.dispose()


def test_modern_install_persists_real_remapped_ports():
    """Do not publish wrong client URLs after the remote port preflight."""
    src = (ROOT / "app/routers/modern_protocol_admin_v3.py").read_text()
    start = src.index('remaps = (result.get("core") or {}).get("port_remaps") or {}')
    end = src.index("        db.commit()", start)
    body = src[start:end]
    assert 'applied_port = int(remap.get("to") or health.get("port") or requested_port)' in body
    assert 'health["port"] = applied_port' in body
    assert "_save_status(db, node, key, health)" in body
    assert "_save_setting(db, node.id, key, preset, effective, applied_port)" in body


def test_standalone_runtime_activates_all_four_adapters():
    from app.standalone_protocol_runtime import STANDALONE_PROTOCOLS
    assert STANDALONE_PROTOCOLS == {
        "mieru", "trusttunnel", "amneziawg", "sudoku",
    }
    assert all(PROTOCOL_CATALOG[key]["runtime_status"] == "ready"
               for key in STANDALONE_PROTOCOLS)



def test_live_health_gate_checks_all_16_with_one_connection():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from app.models import NodeType
    from app.services import new_node_readiness_v1 as readiness

    class DummyDB:
        def get(self, model, id):
            return SimpleNamespace(node_type=NodeType.EXIT, retired_at=None)
        def query(self, model):
            return self
        def filter(self, *clauses):
            return self
        def all(self):
            return [
                SimpleNamespace(protocol=key, status="online", port=15000 + n)
                for n, key in enumerate(ALL_PROTOCOL_KEYS)
            ]

    conn = SimpleNamespace(
        close=lambda: None,
        wait_closed=AsyncMock(return_value=None),
    )
    db = DummyDB()
    with (
        patch.object(readiness, "connect_protocol_runtime",
                     new_callable=AsyncMock, return_value=conn) as connect,
        patch.object(readiness, "_protocol_live_health",
                     new_callable=AsyncMock, return_value={"ok": True}) as classic,
        patch.object(readiness, "profile_health",
                     new_callable=AsyncMock, return_value={"ok": True}) as modern,
    ):
        result = asyncio.run(readiness.verify_new_exit_readiness(db, 123))
        assert result == {
            "ok": True, "reason": "ready", "ready_count": 16,
            "required_count": 16, "missing": [],
        }
        assert connect.await_count == 1
        assert classic.await_count == 5
        assert modern.await_count == 11
        assert conn.wait_closed.await_count == 1


def test_live_health_gate_refuses_one_failing_protocol():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from app.models import NodeType
    from app.services import new_node_readiness_v1 as readiness

    class DummyDB:
        def get(self, model, id):
            return SimpleNamespace(node_type=NodeType.EXIT, retired_at=None)
        def query(self, model):
            return self
        def filter(self, *clauses):
            return self
        def all(self):
            return [
                SimpleNamespace(protocol=key, status="online", port=15000 + n)
                for n, key in enumerate(ALL_PROTOCOL_KEYS)
            ]

    conn = SimpleNamespace(
        close=lambda: None,
        wait_closed=AsyncMock(return_value=None),
    )

    async def modern_health(_conn, protocol, _port):
        return {"ok": protocol != "sudoku"}

    with (
        patch.object(readiness, "connect_protocol_runtime",
                     new_callable=AsyncMock, return_value=conn),
        patch.object(readiness, "_protocol_live_health",
                     new_callable=AsyncMock, return_value={"ok": True}),
        patch.object(readiness, "profile_health", side_effect=modern_health),
    ):
        result = asyncio.run(readiness.verify_new_exit_readiness(DummyDB(), 123))
        assert result["ok"] is False
        assert result["missing"] == ["sudoku"]
        assert result["ready_count"] == 15


def test_hidden_node_is_not_published_when_install_failed():
    src = (ROOT / "app/routers/publish_node_all_users_v1.py").read_text()
    body = src.split("async def _install_node_in_background(", 1)[1].split(
        '@router.post("/install-background-v1"', 1
    )[0]
    assert body.index('if failed_classic:') < body.index(
        "await publish_node_to_all_users_v2("
    )
    assert body.index('if missing or not modern_bootstrap.get("ok"):') < body.index(
        "await publish_node_to_all_users_v2("
    )
    assert body.index('if not live.get("ok"):') < body.index(
        "await publish_node_to_all_users_v2("
    )
