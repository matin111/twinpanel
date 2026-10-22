from __future__ import annotations

from datetime import datetime

import pytest

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.manual_authority_manager_guard_v195 import (
    install_manual_authority_manager_guard_v195,
    remove_manual_authority_manager_guard_v195,
)
from app.models import (
    Node,
    NodeStatus,
    NodeType,
    Tunnel,
    TunnelPeerState,
    TunnelStatus,
    TunnelTransport,
)
from app.routers.manual_authority_v193 import report_tunnel_peer_v193
from app.schemas import TunnelPeerReportIn


IRAN_ID = 95101
EXIT_ID = 95102
TUNNEL_ID = 95103
ADMIN_SWITCH_AT = datetime(2026, 10, 22, 18, 0, 0)
STALE_MANAGER_SWITCH_AT = datetime(2026, 10, 22, 18, 0, 30)


@pytest.fixture(autouse=True)
def manual_authority_guard():
    install_manual_authority_manager_guard_v195()
    yield
    remove_manual_authority_manager_guard_v195()


def _prepare_schema_and_rows() -> None:
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Node.__table__,
            Tunnel.__table__,
            TunnelTransport.__table__,
            TunnelPeerState.__table__,
        ],
    )

    db = SessionLocal()
    try:
        (
            db.query(TunnelPeerState)
            .filter(TunnelPeerState.tunnel_id == TUNNEL_ID)
            .delete(synchronize_session=False)
        )
        (
            db.query(TunnelTransport)
            .filter(TunnelTransport.tunnel_id == TUNNEL_ID)
            .delete(synchronize_session=False)
        )
        db.query(Tunnel).filter(Tunnel.id == TUNNEL_ID).delete(
            synchronize_session=False
        )
        db.query(Node).filter(Node.id.in_([IRAN_ID, EXIT_ID])).delete(
            synchronize_session=False
        )
        db.commit()

        db.add_all(
            [
                Node(
                    id=IRAN_ID,
                    name="manual-authority-v195-iran",
                    node_type=NodeType.IRAN,
                    country_code="IR",
                    public_ip="192.0.2.101",
                    agent_url="http://192.0.2.101:8099",
                    status=NodeStatus.ONLINE,
                ),
                Node(
                    id=EXIT_ID,
                    name="manual-authority-v195-exit",
                    node_type=NodeType.EXIT,
                    country_code="DE",
                    public_ip="192.0.2.102",
                    agent_url="http://192.0.2.102:8099",
                    status=NodeStatus.ONLINE,
                ),
            ]
        )
        db.flush()

        db.add(
            Tunnel(
                id=TUNNEL_ID,
                iran_node_id=IRAN_ID,
                exit_node_id=EXIT_ID,
                transport="ssh_tun",
                mode="auto",
                preferred_transport="quic_2027",
                active_transport="backhaul",
                status=TunnelStatus.ONLINE,
                latency_ms=22,
                is_active=True,
            )
        )
        db.flush()

        db.add_all(
            [
                TunnelTransport(
                    tunnel_id=TUNNEL_ID,
                    transport="tp27_fast",
                    priority=5,
                    enabled=True,
                    status="online",
                    latency_ms=18,
                ),
                TunnelTransport(
                    tunnel_id=TUNNEL_ID,
                    transport="ssh_tun",
                    priority=200,
                    enabled=True,
                    status="online",
                    latency_ms=22,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()


def _cleanup_rows() -> None:
    db = SessionLocal()
    try:
        (
            db.query(TunnelPeerState)
            .filter(TunnelPeerState.tunnel_id == TUNNEL_ID)
            .delete(synchronize_session=False)
        )
        (
            db.query(TunnelTransport)
            .filter(TunnelTransport.tunnel_id == TUNNEL_ID)
            .delete(synchronize_session=False)
        )
        db.query(Tunnel).filter(Tunnel.id == TUNNEL_ID).delete(
            synchronize_session=False
        )
        db.query(Node).filter(Node.id.in_([IRAN_ID, EXIT_ID])).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def test_production_race_manual_admin_beats_agent_and_stale_manager_writer():
    _prepare_schema_and_rows()

    manager_db = SessionLocal()
    try:
        # Step 1/2: the old manager cycle starts while the Tunnel is still Auto
        # and keeps this ORM instance stale across long remote probes.
        stale_tunnel = manager_db.get(Tunnel, TUNNEL_ID)
        assert stale_tunnel is not None
        assert stale_tunnel.mode == "auto"
        assert stale_tunnel.active_transport == "backhaul"

        # Step 3: Admin explicitly selects tp27_fast in Manual mode.
        admin_db = SessionLocal()
        try:
            current = admin_db.get(Tunnel, TUNNEL_ID)
            assert current is not None
            current.mode = "manual"
            current.preferred_transport = "tp27_fast"
            current.active_transport = "tp27_fast"
            current.last_switch_at = ADMIN_SWITCH_AT
            current.status = TunnelStatus.ONLINE
            current.latency_ms = 18
            admin_db.commit()
        finally:
            admin_db.close()

        # Step 4: an Agent still reports its old ssh_tun selection. V193 must
        # keep that as peer/member telemetry without taking aggregate authority.
        agent_db = SessionLocal()
        try:
            response = report_tunnel_peer_v193(
                TUNNEL_ID,
                IRAN_ID,
                TunnelPeerReportIn(
                    selected_transport="ssh_tun",
                    endpoint_reachable=True,
                    tunnel_reachable=True,
                    latency_ms=61,
                    last_error=None,
                ),
                x_node_secret=settings.node_agent_shared_secret,
                db=agent_db,
            )
            assert response["telemetry_only"] is True
            assert response["active_transport"] == "tp27_fast"
            assert response["preferred_transport"] == "tp27_fast"
        finally:
            agent_db.close()

        # Step 5: the stale Auto cycle finishes later and tries to restore SSH.
        # Health telemetry is allowed, but authority fields must be rejected.
        stale_tunnel.active_transport = "ssh_tun"
        stale_tunnel.preferred_transport = "ssh_tun"
        stale_tunnel.last_switch_at = STALE_MANAGER_SWITCH_AT
        stale_tunnel.status = TunnelStatus.DEGRADED
        stale_tunnel.latency_ms = 88
        manager_db.commit()

        verify_db = SessionLocal()
        try:
            final = verify_db.get(Tunnel, TUNNEL_ID)
            assert final is not None
            assert final.mode == "manual"
            assert final.preferred_transport == "tp27_fast"
            assert final.active_transport == "tp27_fast"
            assert final.last_switch_at == ADMIN_SWITCH_AT

            # Manual authority does not suppress health telemetry.
            assert final.status == TunnelStatus.DEGRADED
            assert final.latency_ms == 88

            peer = (
                verify_db.query(TunnelPeerState)
                .filter(
                    TunnelPeerState.tunnel_id == TUNNEL_ID,
                    TunnelPeerState.node_id == IRAN_ID,
                )
                .one()
            )
            assert peer.selected_transport == "ssh_tun"
            assert peer.endpoint_reachable is True
            assert peer.tunnel_reachable is True
            assert peer.latency_ms == 61
        finally:
            verify_db.close()
    finally:
        manager_db.close()
        _cleanup_rows()


def test_manager_guard_is_activated_before_manager_workers_start():
    source = __import__(
        "inspect"
    ).getsource(
        __import__(
            "app.manager_runtime_v16",
            fromlist=["install_manager_runtime_v16"],
        ).install_manager_runtime_v16
    )

    guard_pos = source.index("install_manual_authority_manager_guard_v195()")
    runtime_pos = source.index("apply_self_hosted_runtime(")
    policy_pos = source.index("install_transport_policy_v16()")

    assert guard_pos < runtime_pos < policy_pos
