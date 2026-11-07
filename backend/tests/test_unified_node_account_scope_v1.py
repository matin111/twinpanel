"""Unified migrated/native account selection is optional and missing-only."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.migration_import_models import MigrationImportRecord
from app.models import (
    Node, NodeProtocolConfig, NodeStatus, NodeType, ProtocolCredential,
    Subscription, SubscriptionNode, SubscriptionProtocol, SubscriptionStatus,
)
from scripts.twinpanel_existing_node_backfill_v1 import eligible_count, parse_args
from scripts.twinpanel_migration_singbox_batch import pending_for_node
from scripts.twinpanel_node_auto_backfill_v1 import (
    _unified_all_active_enabled, execute_one,
)


def fixture():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[
        Node.__table__, Subscription.__table__, SubscriptionNode.__table__,
        SubscriptionProtocol.__table__, ProtocolCredential.__table__,
        NodeProtocolConfig.__table__, MigrationImportRecord.__table__,
    ])
    db = Session(engine)
    node = Node(
        id=77, name="New Exit", node_type=NodeType.EXIT, country_code="DE",
        public_ip="192.0.2.77", agent_url="https://192.0.2.77:9443",
        status=NodeStatus.ONLINE, show_to_users=True,
    )
    db.add(node)
    db.add(NodeProtocolConfig(
        id=900, node_id=77, protocol="hysteria2", status="online", port=8444,
    ))
    for id in range(101, 108):
        db.add(Subscription(
            id=id, user_id=id, plan_id=1,
            status=SubscriptionStatus.PENDING if id == 105 else SubscriptionStatus.ACTIVE,
            expires_at=datetime.utcnow()-timedelta(days=1) if id == 103 else None,
            traffic_limit_bytes=100, traffic_used_bytes=100 if id == 104 else 0,
        ))
        db.add(SubscriptionNode(
            id=1000+id, node_id=77 if id != 107 else 88,
            subscription_id=id,
        ))
        # Only subscribed protocol entitlements are honored.
        if id != 106:
            db.add(SubscriptionProtocol(id=2000+id, subscription_id=id, protocol="openvpn"))
        if id in (101, 102, 103, 104):
            db.add(SubscriptionProtocol(id=3000+id, subscription_id=id, protocol="hysteria2"))
    db.add(MigrationImportRecord(
        id=10, source="eylan", source_id="eylan-101",
        subscription_id=101, preserved_payload_encrypted="opaque",
    ))
    db.commit()
    return engine, db, node


def test_all_active_includes_migrated_and_new_without_expired_or_exhausted():
    engine, db, _ = fixture()
    try:
        assert eligible_count(db, 77, "openvpn") == 1
        assert eligible_count(db, 77, "openvpn", include_all_active=True) == 2
        assert eligible_count(db, 77, "openvpn", subscription_id=101,
                              include_all_active=True) == 1
        assert eligible_count(db, 77, "openvpn", subscription_id=106,
                              include_all_active=True) == 0
    finally:
        db.close()
        engine.dispose()


def test_singbox_one_missing_only_scope_for_migrated_and_created():
    engine, db, node = fixture()
    try:
        with patch("app.routers.account_delivery._delivery_item_is_usable", return_value=True):
            imported = pending_for_node(db, node)
            unified = pending_for_node(db, node, include_all_active=True)
        assert {(sub.id, proto) for sub,proto,*_ in imported} == {(101,"hysteria2")}
        assert {(sub.id, proto) for sub,proto,*_ in unified} == {
            (101,"hysteria2"), (102,"hysteria2"),
        }
    finally:
        db.close()
        engine.dispose()


def test_rollout_requires_explicit_optin_and_existing_confirmed_node():
    assert parse_args(["--node-id","77","--protocol","openvpn"]).include_all_active is False
    options = parse_args([
        "--node-id","77","--protocol","openvpn","--include-all-active",
        "--apply","--confirm-node-id","77",
    ])
    assert options.include_all_active and options.apply
    with patch.dict(os.environ, {}, clear=True):
        assert not _unified_all_active_enabled()
    with patch.dict(os.environ, {"TWINPANEL_UNIFIED_NODE_BACKFILL_V1": "1"}):
        assert _unified_all_active_enabled()


def test_unified_supervisor_explicitly_passes_one_scope_not_new_worker():
    output = "NODE_BACKFILL_CYCLE {'new_pairs': 1, 'cycle': 1}\n"
    completed = SimpleNamespace(returncode=0, stdout=output)
    with patch.dict(os.environ, {"TWINPANEL_UNIFIED_NODE_BACKFILL_V1":"1"}, clear=True):
        with patch("scripts.twinpanel_node_auto_backfill_v1.subprocess.run", return_value=completed) as run:
            assert execute_one(77,"openvpn") == (1,None)
            args = run.call_args.args[0]
            assert "--include-all-active" in args
            assert "--confirm-node-id" in args
            assert args[args.index("--confirm-node-id")+1] == "77"
    with patch.dict(os.environ, {}, clear=True):
        with patch("scripts.twinpanel_node_auto_backfill_v1.subprocess.run", return_value=completed) as run:
            assert execute_one(77,"openvpn") == (1,None)
            assert "--include-all-active" not in run.call_args.args[0]
