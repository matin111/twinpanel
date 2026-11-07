"""Isolated tests: one central active-account queue, no real SSH or node writes."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import (
    Node, NodeProtocolConfig, NodeStatus, NodeType, Plan, ProtocolCredential,
    Subscription, SubscriptionNode, SubscriptionProtocol, SubscriptionStatus, User,
)
from app.migration_import_models import MigrationImportRecord
from app.services.node_auto_backfill_v1 import FAMILIES, enqueue_node_backfill
from app.node_backfill_job_models_v1 import NodeBackfillJobV1
from scripts.twinpanel_node_auto_backfill_v1 import (
    _unified_all_active_enabled, execute_one,
)
from scripts.twinpanel_standalone_node_backfill_v1 import (
    pending_for_node, MAX_STANDALONE_PAIRS_PER_CYCLE,
)
from scripts.twinpanel_existing_node_backfill_v1 import parse_args


ROOT = Path(__file__).resolve().parents[1]


def fixture():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[
        Node.__table__, Plan.__table__, User.__table__,
        Subscription.__table__, SubscriptionNode.__table__,
        SubscriptionProtocol.__table__, ProtocolCredential.__table__,
        NodeProtocolConfig.__table__, MigrationImportRecord.__table__,
        NodeBackfillJobV1.__table__,
    ])
    db = Session(engine)
    db.add(Node(
        id=13, name="Test Exit", country_code="DE", node_type=NodeType.EXIT,
        public_ip="192.0.2.13", agent_url="https://192.0.2.13:9443",
        status=NodeStatus.ONLINE, show_to_users=True,
    ))
    db.add(Plan(id=1, name="Test", duration_days=30, traffic_gb=10, price_toman=1000))
    for i in [1, 2, 3]:
        db.add(User(id=i, email=f"user{i}@example.invalid", password_hash="dummy"))
    db.flush()
    now = datetime.utcnow()
    for i, status, expires in [
        (1, SubscriptionStatus.ACTIVE, now + timedelta(days=10)),
        (2, SubscriptionStatus.ACTIVE, now + timedelta(days=10)),
        (3, SubscriptionStatus.EXPIRED, now - timedelta(days=1)),
    ]:
        db.add(Subscription(
            id=100 + i, user_id=i, plan_id=1, status=status,
            expires_at=expires, traffic_limit_bytes=10_000,
            traffic_used_bytes=0,
        ))
        db.add(SubscriptionNode(id=200 + i, subscription_id=100 + i, node_id=13))
        db.add(SubscriptionProtocol(id=300 + i, subscription_id=100 + i, protocol="mieru"))
    db.add(MigrationImportRecord(
        id=501, source="eylan", source_id="old-101", subscription_id=101,
        preserved_payload_encrypted="dummy",
    ))
    db.add(NodeProtocolConfig(
        id=400, node_id=13, protocol="mieru", port=8450, status="online",
    ))
    db.commit()
    return engine, db


def test_imported_and_native_share_same_active_entitlement_scope():
    engine, db = fixture()
    try:
        node = db.get(Node, 13)
        migrated = pending_for_node(db, node, 20, include_all_active=False)
        unified = pending_for_node(db, node, 20, include_all_active=True)
        assert [(sub.id, protocol) for sub, protocol, *_ in migrated] == [(101, "mieru")]
        assert [(sub.id, protocol) for sub, protocol, *_ in unified] == [
            (101, "mieru"), (102, "mieru"),
        ]
        assert 103 not in {sub.id for sub, *_ in unified}
    finally:
        db.close()
        engine.dispose()


def test_backfill_has_one_job_family_for_all_16_protocols():
    engine, db = fixture()
    try:
        assert FAMILIES == (
            "singbox", "standalone", "openvpn", "cisco",
            "wireguard", "l2tp", "v2ray",
        )
        jobs = enqueue_node_backfill(db, 13)
        db.commit()
        assert len(jobs) == 7
        assert "standalone" in {row.protocol for row in jobs}
        assert len(enqueue_node_backfill(db, 13)) == len(jobs)
    finally:
        db.close()
        engine.dispose()


def test_auto_worker_defaults_to_unified_and_supports_emergency_optout():
    with patch.dict(os.environ, {}, clear=True):
        assert _unified_all_active_enabled()
    with patch.dict(os.environ, {"TWINPANEL_UNIFIED_NODE_BACKFILL_V1": "0"}):
        assert not _unified_all_active_enabled()
    with patch.dict(os.environ, {}, clear=True):
        with patch(
            "scripts.twinpanel_node_auto_backfill_v1.subprocess.run",
            return_value=SimpleNamespace(
                returncode=0,
                stdout="NODE_BACKFILL_CYCLE {'new_pairs': 2, 'cycle': 1}\n",
            ),
        ) as invoke:
            assert execute_one(13, "standalone") == (2, None)
            args = invoke.call_args.args[0]
            assert "--include-all-active" in args
            assert args[args.index("--protocol") + 1] == "standalone"
            assert "--confirm-node-id" in args


def test_standalone_dry_run_and_hard_batch_limit():
    assert MAX_STANDALONE_PAIRS_PER_CYCLE <= 3
    assert parse_args(["--node-id", "13", "--protocol", "standalone"]).apply is False
    code = (ROOT / "scripts/twinpanel_standalone_node_backfill_v1.py").read_text()
    assert "SubscriptionProvisioningGuard" in code
    assert "if cred is not None and cred.config_text_encrypted and not items:" in code
    assert "if any(ad._autosync_item_node_id(item) == int(node.id) for item in items):" in code
    assert "merged.append(item)" in code
    assert "cred.secret_encrypted = ad._enc(secret_to_dict(secret))" in code
    assert "if protocol == \"amneziawg\":" in code
    assert 'print("STANDALONE_NODE_PAIR_ERROR"' in code
    assert "str(exc)" not in code


def test_install_requires_all_sixteen_real_health_checks_before_publish():
    code = (ROOT / "app/routers/publish_node_all_users_v1.py").read_text()
    body = code.split("async def _install_node_in_background(", 1)[1].split(
        '@router.post("/install-background-v1"', 1
    )[0]
    assert body.index('await install_node(') < body.index('await ensure_classic_protocol(')
    assert body.index('await ensure_classic_protocol(') < body.index('await bootstrap_new_exit_modern_protocols(')
    assert body.index("await verify_new_exit_readiness(db, node_id)") < body.index(
        "await publish_node_to_all_users(node_id=node_id, db=db)"
    )
    assert "if not ready:" in body
    assert body.index("if not ready:") < body.index(
        "await publish_node_to_all_users(node_id=node_id, db=db)"
    )
    assert "defer_subscription_sync=True" in body
