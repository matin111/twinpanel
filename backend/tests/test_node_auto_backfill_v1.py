"""Durable auto-backfill behavior: no live credentials, nodes or SSH used."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeStatus, NodeType
from app.node_backfill_job_models_v1 import NodeBackfillJobV1
from app.services.node_auto_backfill_v1 import (
    FAMILIES, claim_next, enqueue_node_backfill, finish_claim, job_status,
)
from scripts.twinpanel_node_auto_backfill_v1 import parsed_pair_count

BASE = Path(__file__).resolve().parents[1]


def fixture_db():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[Node.__table__, NodeBackfillJobV1.__table__])
    db = Session(engine)
    db.add(Node(id=13, name="Germany Exit", node_type=NodeType.EXIT,
                country_code="DE", public_ip="192.0.2.13",
                agent_url="https://192.0.2.13:9443",
                status=NodeStatus.ONLINE, show_to_users=True))
    db.commit()
    return engine, db


def test_enqueue_is_idempotent_and_no_xray():
    engine, db = fixture_db()
    try:
        a = enqueue_node_backfill(db, 13)
        db.commit()
        b = enqueue_node_backfill(db, 13)
        db.commit()
        assert len(a) == len(b) == 5
        assert set(x.protocol for x in b) == set(FAMILIES)
        assert not set(FAMILIES).intersection({"v2ray", "xray", "reality"})
        assert db.query(NodeBackfillJobV1).count() == 5
        status = job_status(db, 13)
        assert status["queued"] and status["completed_pairs"] == 0
    finally:
        db.close()
        engine.dispose()


def test_claim_then_progress_retry_done_and_preserve_stale_token():
    engine, db = fixture_db()
    try:
        enqueue_node_backfill(db, 13)
        db.commit()
        first = claim_next(db)
        assert first is not None
        node_id, protocol, token = first
        assert node_id == 13 and protocol in FAMILIES
        assert not finish_claim(db, 13, protocol, "wrong-token", count=20)
        assert finish_claim(db, 13, protocol, token, count=20)
        row = db.get(NodeBackfillJobV1, (13, protocol))
        assert row.completed_pairs == 20 and row.state == "queued"
        # Other queued families take priority over the delayed partial job.
        requeued = claim_next(db, now=dt.datetime.utcnow() + dt.timedelta(seconds=120))
        assert requeued
        assert finish_claim(db, *requeued, count=0)
        assert db.get(NodeBackfillJobV1, (requeued[0], requeued[1])).state == "done"
    finally:
        db.close()
        engine.dispose()


def test_errors_retry_without_wiping_previous_progress():
    engine, db = fixture_db()
    try:
        enqueue_node_backfill(db, 13)
        db.commit()
        a = claim_next(db)
        assert a
        assert finish_claim(db, *a, count=0, error_code="BACKFILL_EXIT_3")
        row = db.get(NodeBackfillJobV1, (a[0], a[1]))
        assert row.state == "retry" and row.error_code == "BACKFILL_EXIT_3"
        assert claim_next(db, now=dt.datetime.utcnow() + dt.timedelta(minutes=2))
    finally:
        db.close()
        engine.dispose()


def test_unpublished_node_will_not_enqueue_or_run():
    engine, db = fixture_db()
    try:
        node = db.get(Node, 13)
        node.show_to_users = False
        db.commit()
        try:
            enqueue_node_backfill(db, 13)
            raise AssertionError("not published")
        except ValueError:
            pass
        node.show_to_users = True
        enqueue_node_backfill(db, 13)
        db.commit()
        node.status = NodeStatus.OFFLINE
        db.commit()
        assert claim_next(db) is None
    finally:
        db.close()
        engine.dispose()


def test_sanitized_progress_marker_and_no_secrets_in_console():
    assert parsed_pair_count("NODE_BACKFILL_CYCLE {'new_pairs': 20, 'cycle': 1}\n") == 20
    assert parsed_pair_count("NODE_BACKFILL_CYCLE {'new_pairs': 200}\n") is None
    assert parsed_pair_count("random output and account passwords") is None
    worker = (BASE / "scripts/twinpanel_node_auto_backfill_v1.py").read_text()
    assert "capture_output=True" in worker
    assert "NODE_AUTO_BACKFILL_RESULT" in worker
    assert "print(proc.stdout)" not in worker


def test_real_http_never_invokes_ssh_and_systemd_installer_is_present():
    publish = (BASE / "app/routers/publish_node_all_users_v2.py").read_text()
    section = publish.split("async def publish_node_to_all_users_v2(", 1)[1].split("@router.post(",1)[0]
    assert "enqueue_node_backfill(db, int(node.id))" in section
    assert section.index("enqueue_node_backfill(db, int(node.id))") < section.index("db.commit()")
    assert "await _sync_modern_node" not in section
    assert "await sync_installed_node_to_subscriptions" not in section
    public_updater = (BASE / "scripts/twinpanel_public_updater.py").read_text()
    assert "install_node_auto_backfill_timer(final)" in public_updater
    installer = (BASE.parent / "installer/install.sh").read_text()
    assert "systemctl enable --now twinpanel-node-auto-backfill.timer" in installer
