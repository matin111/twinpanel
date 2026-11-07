"""Guarded 16-protocol node fanout: imported and native accounts share scope."""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.migration_import_models import MigrationImportRecord
from app.models import (
    Node, NodeProtocolConfig, NodeStatus, NodeType, ProtocolCredential,
    Subscription, SubscriptionNode, SubscriptionProtocol, SubscriptionStatus,
)
from app.node_backfill_job_models_v1 import NodeBackfillJobV1
from app.node_backfill_scope_models_v1 import NodeBackfillScopeV1
from app.services.node_auto_backfill_v1 import FAMILIES, enqueue_node_backfill
from app.standalone_subscription_accounts import StandaloneAccountSecret
from scripts import twinpanel_standalone_node_backfill_v1 as standalone
from scripts.twinpanel_existing_node_backfill_v1 import eligible_count, parse_args
from scripts import twinpanel_node_auto_backfill_v1 as supervisor


def fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[
        Node.__table__, NodeProtocolConfig.__table__,
        Subscription.__table__, SubscriptionNode.__table__,
        SubscriptionProtocol.__table__, ProtocolCredential.__table__,
        MigrationImportRecord.__table__, NodeBackfillScopeV1.__table__,
        NodeBackfillJobV1.__table__,
    ])
    db = Session(engine)
    node = Node(
        id=77, name="New Exit", node_type=NodeType.EXIT, country_code="DE",
        public_ip="192.0.2.77", agent_url="https://192.0.2.77:9443",
        status=NodeStatus.ONLINE, show_to_users=True,
    )
    db.add(node)
    db.add(NodeProtocolConfig(
        id=700, node_id=77, protocol="mieru", status="online", port=8450,
    ))
    for sid in range(101, 107):
        db.add(Subscription(
            id=sid, user_id=sid, plan_id=1,
            status=SubscriptionStatus.PENDING if sid == 105 else SubscriptionStatus.ACTIVE,
            expires_at=datetime.utcnow()-timedelta(days=1) if sid == 103 else None,
            traffic_limit_bytes=100, traffic_used_bytes=100 if sid == 104 else 0,
        ))
        db.add(SubscriptionNode(id=500+sid, subscription_id=sid, node_id=77))
        if sid != 106:
            db.add(SubscriptionProtocol(
                id=800+sid, subscription_id=sid, protocol="mieru",
            ))
    db.add(MigrationImportRecord(
        id=111, source="eylan", source_id="import-101",
        subscription_id=101, preserved_payload_encrypted="opaque",
    ))
    db.commit()
    return engine, db, node


def _decode(value):
    return json.loads(value) if value else None


def test_old_exit_keeps_six_jobs_new_published_exit_has_seven():
    engine, db, node = fixture()
    try:
        assert len(enqueue_node_backfill(db, node.id)) == 6
        db.commit()
        assert db.get(NodeBackfillJobV1, (77, "standalone")) is None
        db.add(NodeBackfillScopeV1(node_id=77, include_all_active=True))
        db.flush()
        jobs = enqueue_node_backfill(db, 77)
        db.commit()
        assert len(jobs) == 7
        assert set(job.protocol for job in jobs) == set(FAMILIES)
        assert db.get(NodeBackfillJobV1, (77, "standalone")) is not None
    finally:
        db.close()
        engine.dispose()


def test_same_standalone_scope_for_migrated_native_and_expiry_quota():
    engine, db, node = fixture()
    try:
        with patch.object(standalone.ad, "_dec", side_effect=_decode):
            old = standalone.pending_for_node(db, node)
            unified = standalone.pending_for_node(db, node, include_all_active=True)
        assert [(sub.id, proto) for sub, proto, *_ in old] == [(101, "mieru")]
        assert [(sub.id, proto) for sub, proto, *_ in unified] == [
            (101, "mieru"), (102, "mieru"),
        ]
        assert eligible_count(db, node.id, "standalone") == 1
        assert eligible_count(db, node.id, "standalone", include_all_active=True) == 2
    finally:
        db.close()
        engine.dispose()


def test_missing_only_keeps_old_node_config_and_never_rotates_identity():
    engine, db, node = fixture()
    # BigInteger PK in production is allocated by Postgres. SQLite test
    # fixtures use explicit ids so the regression tests avoid AUTOINCREMENT
    # differences unrelated to the actual node worker.
    db.add(ProtocolCredential(
        id=2101, subscription_id=101, protocol="mieru",
    ))
    db.add(ProtocolCredential(
        id=2102, subscription_id=102, protocol="mieru",
        username="tp-sub-102",
        secret_encrypted=json.dumps({
            "protocol": "mieru", "subscription_id": 102,
            "username": "tp-sub-102", "password": "existing-secret",
        }),
        config_text_encrypted=json.dumps([
            {"node_id": 88, "uri": "old-node-configuration"},
        ]),
    ))
    db.commit()
    connection = SimpleNamespace(
        close=lambda: None, wait_closed=AsyncMock(return_value=None),
    )
    try:
        with (
            patch.object(standalone, "SessionLocal", side_effect=lambda: Session(engine)),
            patch.object(standalone, "SubscriptionProvisioningGuard",
                         side_effect=lambda _: contextlib.nullcontext()),
            patch.object(standalone.ad, "_dec", side_effect=_decode),
            patch.object(standalone.ad, "_enc", side_effect=json.dumps),
            patch.object(standalone.ad, "ssh_connect_saved",
                         new_callable=AsyncMock, return_value=connection),
            patch.object(standalone, "new_account_secret", new_callable=AsyncMock,
                         return_value=StandaloneAccountSecret(
                             protocol="mieru", subscription_id=101,
                             username="tp-sub-101", password="new-secret",
                         )) as fresh,
            patch.object(standalone, "apply_account", new_callable=AsyncMock,
                         side_effect=lambda _, node, secret, port: {
                             "node_id": node.id, "port": port,
                             "username": secret.username, "uri": "new-node",
                         }) as apply,
        ):
            assert asyncio.run(standalone.run_one_node(
                77, include_all_active=True, max_pairs=2,
            )) == 2
            assert apply.await_count == 2
            assert fresh.await_count == 1
            saved = db.query(ProtocolCredential).filter(
                ProtocolCredential.subscription_id == 102,
                ProtocolCredential.protocol == "mieru",
            ).one()
            db.refresh(saved)
            assert _decode(saved.secret_encrypted)["password"] == "existing-secret"
            items = _decode(saved.config_text_encrypted)
            assert len(items) == 2
            assert items[0] == {"node_id": 88, "uri": "old-node-configuration"}
            assert items[1]["node_id"] == 77
            # Identical retry: no new SSH, and no changes to either identity.
            assert standalone.pending_for_node(
                db, node, include_all_active=True,
            ) == []
    finally:
        db.close()
        engine.dispose()


def test_unreadable_existing_identity_fails_closed_without_key_regeneration():
    engine, db, node = fixture()
    db.add(ProtocolCredential(
        id=2102, subscription_id=102, protocol="mieru",
        secret_encrypted="invalid-encrypted-payload",
    ))
    db.commit()
    try:
        with patch.object(standalone.ad, "_dec", side_effect=_decode):
            with pytest.raises((RuntimeError, ValueError, json.JSONDecodeError)):
                standalone.pending_for_node(db, node, include_all_active=True)
    finally:
        db.close()
        engine.dispose()


def test_automatic_new_node_scope_and_standalone_are_bounded():
    with patch.dict(os.environ, {"TWINPANEL_UNIFIED_NODE_BACKFILL_V1": "1"}):
        with patch.object(supervisor.subprocess, "run",
                          return_value=SimpleNamespace(
                              returncode=0,
                              stdout="NODE_BACKFILL_CYCLE {'new_pairs': 1, 'cycle': 1}\n",
                          )) as run:
            assert supervisor.execute_one(77, "standalone") == (1, None)
            args = run.call_args.args[0]
            assert "--include-all-active" in args
            assert args[args.index("--max-pairs") + 1] == "1"
            assert args[args.index("--max-cycles") + 1] == "1"
            assert "--confirm-node-id" in args
            assert args[args.index("--confirm-node-id") + 1] == "77"
    assert parse_args(["--node-id", "77", "--protocol", "standalone"]).apply is False
