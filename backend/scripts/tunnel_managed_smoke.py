from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.database import SessionLocal
from app.models import Node, NodeStatus, NodeType, Tunnel, TunnelPeerState, TunnelTransport
from app.routers import tunnel_managed
from app.schemas import TunnelCreate


def _node(db, *, name: str, node_type: NodeType, ip: str) -> Node:
    row = Node(
        name=name,
        node_type=node_type,
        country_code="IR" if node_type == NodeType.IRAN else "DE",
        public_ip=ip,
        agent_url=f"http://{ip}:8787",
        status=NodeStatus.ONLINE,
        current_users=0,
        capacity_users=1000,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _success(name: str, latency: int):
    async def installer(tunnel_id: int, db):
        row = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == tunnel_id,
                TunnelTransport.transport == name,
            )
            .first()
        )
        assert row is not None
        row.enabled = True
        row.status = "online"
        row.latency_ms = latency
        row.last_error = None
        db.commit()
        return {"ok": True, "transport": name, "status": "online"}

    return installer


async def _failure(tunnel_id: int, db):
    raise HTTPException(status_code=502, detail="simulated install failure")


async def _cleanup_without_remote(tunnel_id: int, db):
    db.query(TunnelPeerState).filter(
        TunnelPeerState.tunnel_id == tunnel_id
    ).delete(synchronize_session=False)
    db.query(TunnelTransport).filter(
        TunnelTransport.tunnel_id == tunnel_id
    ).delete(synchronize_session=False)
    tunnel = db.get(Tunnel, tunnel_id)
    if tunnel is not None:
        db.delete(tunnel)
    db.commit()
    return {"ok": True}


async def main() -> None:
    db = SessionLocal()
    original_transports = tunnel_managed._TRANSPORTS
    original_delete = tunnel_managed.core.delete_tunnel

    try:
        iran = _node(
            db,
            name="ci-managed-iran",
            node_type=NodeType.IRAN,
            ip="192.0.2.10",
        )
        exit_node = _node(
            db,
            name="ci-managed-exit",
            node_type=NodeType.EXIT,
            ip="192.0.2.20",
        )

        tunnel_managed._TRANSPORTS = (
            ("mtunnel", 90, _success("mtunnel", 31)),
            ("backhaul", 100, _success("backhaul", 35)),
            ("ssh_tun", 200, _success("ssh_tun", 42)),
        )

        result = await tunnel_managed.create_managed_tunnel(
            TunnelCreate(
                iran_node_id=iran.id,
                exit_node_id=exit_node.id,
                priority=100,
            ),
            db,
        )

        assert result["ok"] is True
        assert result["complete"] is True
        assert result["active_transport"] == "mtunnel"
        assert set(result["installed"]) == {"mtunnel", "backhaul", "ssh_tun"}
        assert result["tunnel"]["status"] == "online"
        assert result["tunnel"]["is_active"] is True

        diagnosis = result.get("diagnosis")
        assert isinstance(diagnosis, dict)
        assert diagnosis.get("backhaul_online") is True
        assert diagnosis.get("direct_online") is True
        assert diagnosis.get("relay_required") is False
        diagnosed = diagnosis.get("transports") or []
        assert len(diagnosed) == 8
        assert {item.get("transport") for item in diagnosed} == {
            "quic_2027",
            "arq_2027",
            "kcp_2027",
            "tcp_2027",
            "mtunnel",
            "backhaul",
            "ssh_tun",
            "ssh_relay",
        }
        relay = next(item for item in diagnosed if item.get("transport") == "ssh_relay")
        assert relay.get("issue_code") == "standby"
        assert relay.get("status") == "standby"

        live = db.get(Tunnel, int(result["tunnel"]["id"]))
        assert live is not None
        assert live.active_transport == "mtunnel"
        assert live.status.value == "online"

        iran_fail = _node(
            db,
            name="ci-managed-iran-fail",
            node_type=NodeType.IRAN,
            ip="192.0.2.30",
        )
        exit_fail = _node(
            db,
            name="ci-managed-exit-fail",
            node_type=NodeType.EXIT,
            ip="192.0.2.40",
        )

        tunnel_managed._TRANSPORTS = (
            ("mtunnel", 90, _failure),
            ("backhaul", 100, _failure),
            ("ssh_tun", 200, _failure),
        )
        tunnel_managed.core.delete_tunnel = _cleanup_without_remote

        try:
            await tunnel_managed.create_managed_tunnel(
                TunnelCreate(
                    iran_node_id=iran_fail.id,
                    exit_node_id=exit_fail.id,
                    priority=100,
                ),
                db,
            )
        except HTTPException as exc:
            assert exc.status_code == 502
            assert isinstance(exc.detail, dict)
            assert exc.detail.get("rolled_back") is True
            errors = exc.detail.get("errors") or {}
            assert "ssh_relay" in errors
        else:
            raise AssertionError("all-failed managed tunnel must fail")

        leftover = (
            db.query(Tunnel)
            .filter(
                Tunnel.iran_node_id == iran_fail.id,
                Tunnel.exit_node_id == exit_fail.id,
            )
            .first()
        )
        assert leftover is None, "failed create left an offline tunnel row"

        print("MANAGED_TUNNEL_SMOKE_OK")

    finally:
        tunnel_managed._TRANSPORTS = original_transports
        tunnel_managed.core.delete_tunnel = original_delete
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
