"""Node admin metrics and installation stages: real counts, no fake online users."""
from __future__ import annotations

import ast
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Node, NodeProtocolConfig, NodeStatus, NodeType, SubscriptionNode
from app.node_install_progress_models_v1 import NodeInstallProgressV1
from app.quota_models import QuotaUsageEvent
from app.routers.node_overview_v1 import configured_ports, node_overview, reported_status
from app.services import node_install_progress_v1 as progress


ROOT = Path(__file__).resolve().parents[1]


def _memory_engine():
    return create_engine("sqlite://", connect_args={"check_same_thread": False},
                         poolclass=StaticPool)


def test_ports_are_unique_and_online_only():
    rows = [
        NodeProtocolConfig(protocol="l2tp", status="online", port=None, port_text="500/4500/1701"),
        NodeProtocolConfig(protocol="wireguard", status="online", port=51820, port_text="51820"),
        NodeProtocolConfig(protocol="openvpn", status="online", port=1194, port_text="1194"),
        NodeProtocolConfig(protocol="xray", status="error", port=8443, port_text="8443"),
        NodeProtocolConfig(protocol="cisco", status="online", port=443, port_text="443"),
    ]
    assert configured_ports(rows) == [443, 500, 1194, 1701, 4500, 51820]


def test_missing_heartbeat_does_not_affect_total_user_count():
    now = datetime.utcnow()
    node = Node(id=99, name="Old heartbeat", node_type=NodeType.EXIT,
                country_code="DE", public_ip="192.0.2.99",
                agent_url="https://192.0.2.99:9443", status=NodeStatus.ONLINE,
                last_seen_at=now-timedelta(minutes=5))
    assert reported_status(node, now) == "offline"


def test_overview_aggregates_assigned_accounts_not_online_sessions():
    engine = _memory_engine()
    Base.metadata.create_all(engine, tables=[
        Node.__table__, SubscriptionNode.__table__,
        NodeProtocolConfig.__table__, QuotaUsageEvent.__table__,
    ])
    try:
        with Session(engine) as db:
            node = Node(
                id=101, name="Stats Exit", node_type=NodeType.EXIT,
                country_code="DE", public_ip="192.0.2.101",
                agent_url="https://192.0.2.101:9443",
                status=NodeStatus.ONLINE, last_seen_at=datetime.utcnow(),
            )
            db.add(node)
            db.add_all([
                SubscriptionNode(id=501, node_id=101, subscription_id=11),
                SubscriptionNode(id=502, node_id=101, subscription_id=12),
                NodeProtocolConfig(id=601, node_id=101, protocol="l2tp",
                                   status="online", port_text="500/4500/1701"),
                NodeProtocolConfig(id=602, node_id=101, protocol="openvpn",
                                   status="online", port=1194, port_text="1194"),
                QuotaUsageEvent(
                    id=701, event_id="evt-1", subscription_id=11, node_id=101,
                    device_id=9, protocol="openvpn", source_key="client-1",
                    counter_mode="cumulative", counter_epoch="initial",
                    source_sequence=1, raw_uplink_value=10, raw_downlink_value=20,
                    uplink_delta=10, downlink_delta=20, billable_bytes=30,
                    accepted_bytes=30, overage_bytes=0,
                    resulting_subscription_status="active",
                    reported_at=datetime.utcnow(),
                ),
                QuotaUsageEvent(
                    id=702, event_id="evt-2", subscription_id=12, node_id=101,
                    device_id=10, protocol="openvpn", source_key="client-2",
                    counter_mode="cumulative", counter_epoch="initial",
                    source_sequence=1, raw_uplink_value=20, raw_downlink_value=40,
                    uplink_delta=20, downlink_delta=40, billable_bytes=60,
                    accepted_bytes=60, overage_bytes=0,
                    resulting_subscription_status="active",
                    reported_at=datetime.utcnow(),
                ),
            ])
            db.commit()
            with patch("app.routers.node_overview_v1.admin_can_use_mother", return_value=True):
                data = node_overview(db=db)
            assert data["users_definition"] == "all_assigned_subscriptions_not_online_sessions"
            assert len(data["items"]) == 1
            row = data["items"][0]
            assert row["users_total"] == 2
            assert row["traffic_bytes"] == 90
            assert row["ports_total"] == 4
            assert row["protocols_online"] == 2
            assert row["status"] == "online"
    finally:
        engine.dispose()


def test_progress_is_durable_and_never_claims_backfill_finished():
    engine = _memory_engine()
    Base.metadata.create_all(engine, tables=[NodeInstallProgressV1.__table__])
    try:
        Maker = sessionmaker(bind=engine, expire_on_commit=False)
        with Maker() as db:
            job_id = progress.create_install_progress(db, "New Exit", True)
        with patch.object(progress, "SessionLocal", Maker):
            progress.set_install_progress(job_id, "installing_base")
            progress.set_install_progress(job_id, "installing_modern", node_id=77,
                                          installed_protocols=12)
            progress.set_install_progress(job_id, "users_queued", node_id=77,
                                          installed_protocols=16, users_assigned=1700)
            # Terminal states must not be overwritten by a delayed callback.
            progress.set_install_progress(job_id, "failed", error_code="LATE_CALLBACK")
        with Maker() as db:
            row = db.get(NodeInstallProgressV1, job_id)
            value = progress.public_install_progress(row)
            assert value["state"] == "completed"
            assert value["stage"] == "users_queued"
            assert value["backfill_pending"] is True
            assert value["users_assigned"] == 1700
            assert value["installed_protocols"] == 16
            assert not hasattr(row, "password")
    finally:
        engine.dispose()


def test_stalled_install_never_shows_success():
    job = NodeInstallProgressV1(
        job_id="00000000-0000-0000-0000-000000000001",
        node_name="Test", state="running", stage="installing_modern",
        updated_at=datetime.utcnow()-timedelta(hours=2),
        created_at=datetime.utcnow()-timedelta(hours=3),
    )
    result = progress.public_install_progress(job)
    assert result["state"] == "interrupted"
    assert result["stage"] == "installing_modern"


def test_frontend_uses_actual_stage_polling_and_no_fake_percentage():
    ui = (ROOT.parent / "components/node-add-modal-bridge.tsx").read_text()
    assert "/v1/nodes/install-jobs/" in ui
    assert "job_id" in ui
    assert "setInterval" in ui
    assert "backfill-status" in ui
    assert "localStorage" in ui
    assert "node-install-running-line" in ui
    assert "percentage" not in ui
    listing = (ROOT.parent / "components/legacy-nodes-runtime-v2.tsx").read_text()
    assert "/v1/nodes/overview-v1" in listing
    assert "users_total" in listing
    assert "traffic_bytes" in listing
    assert "ports_total" in listing


def test_routes_do_not_serialize_secrets():
    route = (ROOT / "app/routers/node_install_progress_v1.py").read_text()
    overview = (ROOT / "app/routers/node_overview_v1.py").read_text()
    for src in (route, overview):
        ast.parse(src)
        assert "Depends(require_admin)" in src
    for src in (
        (ROOT / "app/node_install_progress_models_v1.py").read_text(),
        (ROOT / "app/services/node_install_progress_v1.py").read_text(),
    ):
        ast.parse(src)
        assert "password_encrypted" not in src
        assert "secret_encrypted" not in src
