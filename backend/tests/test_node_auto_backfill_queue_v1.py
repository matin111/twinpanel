"""Automatic historic-node backfill contracts: no real SSH or credentials."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import Node, NodeStatus, NodeType
from app.node_auto_backfill_job_models_v1 import NodeAutoBackfillJobV1
from app.services.node_auto_backfill_queue_v1 import (
    PHASES, claim_job, defer_job, enqueue_published_node, finish_batch,
    job_status, pause_job, renew_lease, resume_job,
)
from app.services import node_auto_backfill_worker_v1 as worker


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Node.__table__.create(engine)
    NodeAutoBackfillJobV1.__table__.create(engine)
    with Session(engine) as session:
        session.add(Node(
            id=191, name="Test Exit", public_ip="192.0.2.191",
            agent_url="https://192.0.2.191:9443",
            country_code="DE", node_type=NodeType.EXIT,
            status=NodeStatus.ONLINE, show_to_users=True,
        ))
        session.commit()
        yield session
    engine.dispose()


def test_publish_is_durable_and_duplicate_clicks_do_not_duplicate_work(db):
    a = enqueue_published_node(db, 191)
    db.commit()
    b = enqueue_published_node(db, 191)
    db.commit()
    assert a.node_id == b.node_id == 191
    assert db.execute(text("SELECT COUNT(*) FROM node_auto_backfill_jobs_v1")).scalar() == 1
    status = job_status(db, 191)
    assert status["state"] == "queued"
    assert status["completed_pairs"] == 0


def test_lease_heartbeat_and_phase_checkpoint(db):
    enqueue_published_node(db, 191)
    db.commit()
    now = datetime.utcnow()
    claim = claim_job(db, now=now)
    assert claim.phase == "singbox"
    assert renew_lease(db, claim, now=now + timedelta(seconds=20))
    assert finish_batch(db, claim, pairs=45, now=now + timedelta(seconds=22))
    assert not finish_batch(db, claim, pairs=45)
    assert job_status(db, 191)["completed_pairs"] == 45
    next_claim = claim_job(db, now=now + timedelta(seconds=30))
    assert next_claim.phase == "singbox"
    assert finish_batch(db, next_claim, pairs=0, now=now + timedelta(seconds=31))
    assert job_status(db, 191)["phase"] == "openvpn"
    assert job_status(db, 191)["completed_pairs"] == 45


def test_expired_lease_recovers_and_old_owner_cannot_update(db):
    enqueue_published_node(db, 191)
    db.commit()
    now = datetime.utcnow()
    old = claim_job(db, now=now)
    recovered = claim_job(db, now=now + timedelta(seconds=600))
    assert recovered.lease_token != old.lease_token
    assert not finish_batch(db, old, pairs=80)
    assert finish_batch(db, recovered, pairs=4, now=now + timedelta(seconds=601))
    assert job_status(db, 191)["completed_pairs"] == 4


def test_pause_waits_for_current_batch_checkpoint_and_resume_is_admin_only(db):
    enqueue_published_node(db, 191)
    db.commit()
    claim = claim_job(db)
    state = pause_job(db, 191)
    assert state["state"] == "pausing"
    assert not claim_job(db)
    assert finish_batch(db, claim, pairs=3)
    state = job_status(db, 191)
    assert state["state"] == "paused"
    assert state["completed_pairs"] == 3
    assert claim_job(db) is None
    assert resume_job(db, 191)["state"] == "queued"
    assert claim_job(db) is not None


def test_transient_defer_does_not_consume_retry_budget(db):
    enqueue_published_node(db, 191)
    db.commit()
    claim = claim_job(db)
    assert defer_job(db, claim, reason="panel_updating", delay_seconds=45)
    assert job_status(db, 191)["consecutive_errors"] == 0
    assert job_status(db, 191)["state"] == "retry"


def test_terminal_state_reports_supported_protocol_scope_only(db):
    enqueue_published_node(db, 191)
    db.commit()
    now = datetime.utcnow()
    for phase in PHASES:
        claim = claim_job(db, now=now)
        assert claim is not None and claim.phase == phase
        assert finish_batch(db, claim, pairs=0, now=now)
        now += timedelta(seconds=10)
    status = job_status(db, 191)
    assert status["state"] == "supported_done"
    assert status["supported_protocols_only"] is True
    assert status["completed_batches"] == len(PHASES)
    assert enqueue_published_node(db, 191).phase == "singbox"
    db.commit()


def test_worker_does_not_claim_when_api_unhealthy():
    with patch.object(worker, "_host_safe_for_backfill", return_value=False), \
         patch.object(worker, "_claim_one") as claim:
        assert asyncio.run(worker.run_one_node_auto_backfill_job()) is False
        claim.assert_not_called()


def test_worker_completes_mocked_batch_without_inline_network(db):
    enqueue_published_node(db, 191)
    db.commit()
    import app.services.node_auto_backfill_queue_v1 as queue
    # The thread-safe SQLite pool lets worker-opened sessions share only
    # test database rows, not a live SQLAlchemy session.
    SessionFactory = lambda: Session(db.get_bind())
    async def mock_batch(claim):
        assert claim.node_id == 191
        return (0, 3)
    with patch.object(worker, "_host_safe_for_backfill", return_value=True), \
         patch.object(worker, "_run_subprocess", side_effect=mock_batch), \
         patch.object(worker, "SessionLocal", new=SessionFactory), \
         patch.object(worker, "HEARTBEAT_SECONDS", new=30):
        assert asyncio.run(worker.run_one_node_auto_backfill_job()) is True
    db.expire_all()
    assert job_status(db, 191)["completed_pairs"] == 3
    assert job_status(db, 191)["completed_batches"] == 1
