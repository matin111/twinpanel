"""Durable node publishing/backfill contracts; never opens real SSH or rewrites users."""
from __future__ import annotations

import asyncio
import ast
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, NodeType
from app.node_auto_backfill_v1 import (
    NodeAutoBackfillJobV1, _claim, _finish, _result_pairs, enabled,
    get_node_auto_backfill_status, pause_node_auto_backfill, queue_backfill,
    status_of, PROTOCOL_STAGES,
)

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[Node.__table__, NodeAutoBackfillJobV1.__table__])
    with Session(engine) as session:
        session.add(Node(
            id=13, name="DE Exit", public_ip="192.0.2.13",
            agent_url="https://192.0.2.13:9443",
            node_type=NodeType.EXIT, country_code="DE",
            status=NodeStatus.ONLINE, show_to_users=True,
        ))
        session.commit()
        yield session
    engine.dispose()


def test_queue_is_durable_idempotent_and_resume_allowed(db):
    row=queue_backfill(db,13)
    db.commit()
    assert row.state=="queued"
    assert db.query(NodeAutoBackfillJobV1).count()==1
    queue_backfill(db,13)
    db.commit()
    assert db.query(NodeAutoBackfillJobV1).count()==1
    first=_claim(db)
    assert first is not None and first[0]==13 and first[2]==0
    token=first[1]
    assert _claim(db) is None
    assert not _finish(db,13,"stale-owner","batch",10,None)
    assert _finish(db,13,token,"batch",10,None)
    job=db.get(NodeAutoBackfillJobV1,13)
    assert job.processed_pairs==10
    assert job.stage_index==0
    assert job.successful_batches==1
    assert job.state=="queued"
    assert status_of(job,node_id=13)["current_protocol"]=="singbox"


def test_batch_progress_and_stage_transition(db):
    queue_backfill(db,13)
    db.commit()
    for index in range(len(PROTOCOL_STAGES)):
        claim=_claim(db)
        assert claim is not None
        assert claim[2]==index
        assert _finish(db,13,claim[1],"next",0,None)
    row=db.get(NodeAutoBackfillJobV1,13)
    assert row.state=="done"
    assert row.stage_index==len(PROTOCOL_STAGES)
    assert status_of(row,node_id=13)["current_protocol"] is None
    assert _claim(db) is None
    queue_backfill(db,13)
    db.commit()
    assert db.get(NodeAutoBackfillJobV1,13).state=="queued"
    assert db.get(NodeAutoBackfillJobV1,13).stage_index==0


def test_pause_during_running_finishes_current_batch(db):
    queue_backfill(db,13)
    db.commit()
    claim=_claim(db)
    assert claim is not None
    stopped=pause_node_auto_backfill(13,db)
    assert stopped["pause_requested"]
    assert _finish(db,13,claim[1],"batch",4,None)
    row=db.get(NodeAutoBackfillJobV1,13)
    assert row.state=="paused"
    assert row.processed_pairs==4
    assert _claim(db) is None
    queue_backfill(db,13)
    db.commit()
    assert not db.get(NodeAutoBackfillJobV1,13).pause_requested


def test_expired_lease_reclaimed_not_old_owner(db):
    from datetime import datetime,timedelta
    queue_backfill(db,13);db.commit()
    first=_claim(db)
    job=db.get(NodeAutoBackfillJobV1,13)
    job.lease_until=datetime.utcnow()-timedelta(seconds=3)
    db.commit()
    second=_claim(db)
    assert second and second[1]!=first[1]
    assert not _finish(db,13,first[1],"batch",20,None)
    assert _finish(db,13,second[1],"batch",4,None)
    assert db.get(NodeAutoBackfillJobV1,13).processed_pairs==4


def test_non_exit_cannot_queue(db):
    db.add(Node(id=14,name="Iran",public_ip="192.0.2.14",agent_url="https://192.0.2.14:9443",country_code="IR",node_type=NodeType.IRAN,status=NodeStatus.ONLINE,show_to_users=True))
    db.commit()
    with pytest.raises(Exception):
        queue_backfill(db,14)


def test_limited_batch_result_never_contains_secret_data():
    assert _result_pairs("NODE_BACKFILL_BATCH_DONE {'node_id': 13, 'new_pairs': 18}") == 18
    assert _result_pairs("NODE_BACKFILL_BATCH_DONE {'node_id': 13, 'new_pairs': 100}") == 20
    with pytest.raises(RuntimeError):
        _result_pairs("this was an SSH password in some unrelated log")


def test_auto_only_on_explicit_publishing_and_flag_off_in_sqlite():
    with patch.dict("os.environ", {"TWINPANEL_AUTO_NODE_BACKFILL_V1":"false"}):
        assert not enabled()
    with patch.dict("os.environ", {"TWINPANEL_AUTO_NODE_BACKFILL_V1":"true"}):
        assert enabled()
    publisher=(BACKEND/"app/routers/publish_node_all_users_v2.py").read_text()
    assert 'queue_backfill(db, int(node.id))' in publisher
    start=publisher.index("async def publish_node_to_all_users_v2(")
    stop=publisher.index("@router.post(",start)
    assert "await _sync_modern_node(" not in publisher[start:stop]
    assert "await sync_installed_node_to_subscriptions(" not in publisher[start:stop]
    script=(BACKEND/"scripts/twinpanel_existing_node_backfill_v1.py").read_text()
    assert "--include-native" in script
    assert "Subscription.traffic_used_bytes < Subscription.traffic_limit_bytes" in script
    main=(BACKEND/"app/main.py").read_text()
    assert "node_auto_backfill_loop()" in main
    assert "node_auto_backfill_task" not in main or "node_backfill_task.cancel()" in main
    assert "node_auto_backfill_v1  # durable node import/native" in main
    for ui in ("legacy-nodes-exact.tsx","legacy-nodes-runtime-v2.tsx"):
        assert "NodeAutoBackfillPanel" in (ROOT/"components"/ui).read_text()


def test_shell_free_subprocess_is_bounded_and_v2ray_excluded():
    file=(BACKEND/"app/node_auto_backfill_v1.py").read_text()
    ast.parse(file)
    assert "asyncio.create_subprocess_exec" in file
    assert "asyncio.to_thread(_preflight, node_id)" in file
    assert "--max-cycles\", \"1\"" in file
    assert '"--include-native"' in file
    assert '"v2ray"' in file
    assert "PROCESS_LOCK" in file
    assert "with_for_update(skip_locked=True)" in file
    assert "node_auto_backfill_loop" in file


def test_native_scope_preserves_default_import_only_and_plan_snapshots():
    modern=(BACKEND/"scripts/twinpanel_migration_singbox_batch.py").read_text()
    classic=(BACKEND/"scripts/twinpanel_migration_classic_sequential_v3.py").read_text()
    assert "include_native: bool = False" in modern
    assert "include_native: bool = False" in classic
    assert "if not include_native:" in modern
    assert "if not include_native:" in classic
    assert "if key not in selected:" in modern
    assert "SubscriptionProtocol.protocol==PROTOCOL" in classic


def test_ui_has_actionable_status_and_protects_customer_secrets():
    client=(ROOT/"components/node-auto-backfill-panel.tsx").read_text()
    assert "auto-backfill-status" in client
    assert "publish-all-users" in client
    assert "auto-backfill-start" in client
    assert "auto-backfill-pause" in client
    assert "password" not in client.lower()
