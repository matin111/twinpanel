"""Progress UI must not treat assigned users as installed account configs."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.services import node_install_progress_v1 as p


def test_backfill_is_nonterminal_and_not_falsely_completed():
    job = SimpleNamespace(
        state="queued", stage="queued", node_id=None, job_id="job",
        node_name="new exit", installed_protocols=None,
        expected_protocols=16, users_assigned=None, error_code=None,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )

    class DummySession:
        def __init__(self):
            self.commits = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def get(self, _model, _job_id):
            return job

        def commit(self):
            self.commits += 1

    store = DummySession()
    with patch.object(p, "SessionLocal", return_value=store):
        p.set_install_progress(
            "job", "users_queued", node_id=77,
            installed_protocols=16, users_assigned=1900,
        )
        assert job.state == "waiting_backfill"
        result = p.public_install_progress(job)
        assert result["state"] == "waiting_backfill"
        assert result["backfill_pending"] is True
        assert result["users_assigned"] == 1900
        assert result["installed_protocols"] == 16

        # An automatic unrelated "completed" update must never make the
        # account queue disappear; that needs its own completion audit.
        assert store.commits == 1
        assert p.TERMINAL == {"completed", "failed", "waiting_backfill"}


def test_real_terminal_install_state_stays_completed():
    job = SimpleNamespace(
        state="completed", stage="completed", node_id=5, job_id="job2",
        node_name="Iran relay", installed_protocols=None,
        expected_protocols=None, users_assigned=None, error_code=None,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    result = p.public_install_progress(job)
    assert result["state"] == "completed"
    assert result["backfill_pending"] is False


def test_node_overview_counts_all_subscriptions_not_live_sessions():
    from app.routers.node_overview_v1 import node_overview
    from app.models import Node, NodeProtocolConfig, NodeStatus, NodeType, SubscriptionNode
    from app.quota_models import QuotaUsageEvent
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool
    from sqlalchemy import create_engine
    from app.database import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[
        Node.__table__, NodeProtocolConfig.__table__,
        SubscriptionNode.__table__, QuotaUsageEvent.__table__,
    ])
    try:
        with Session(engine) as db:
            db.add(Node(
                id=77, name="node", node_type=NodeType.EXIT,
                public_ip="192.0.2.77", agent_url="https://192.0.2.77:9443",
                country_code="DE", status=NodeStatus.OFFLINE,
            ))
            db.add_all([
                SubscriptionNode(id=1, node_id=77, subscription_id=100),
                SubscriptionNode(id=2, node_id=77, subscription_id=101),
            ])
            db.commit()
            with patch("app.routers.node_overview_v1.admin_can_use_mother", return_value=True):
                value = node_overview(db)
            row = value["items"][0]
            assert row["users_total"] == 2
            assert value["users_definition"] == "all_assigned_subscriptions_not_online_sessions"
    finally:
        engine.dispose()
