from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException

from app.database import SessionLocal
from app.models import Node, NodeStatus, NodeType, Tunnel, TunnelPeerState, TunnelTransport
from app.routers import tunnel_managed
from app.runtime_reconciler_v2 import _cleanup_script as cleanup_script_v2
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


async def _skip_tp2027(db, tunnel_id: int, base_online: set[str]):
    return [], {}, {}


def _assert_runtime_cleanup_payload_compiles() -> None:
    script = cleanup_script_v2(9)
    start_marker = "python3 - \"$TID\" <<'PY2'\n"
    end_marker = "\nPY2\n"

    assert start_marker in script
    payload = script.split(start_marker, 1)[1].split(end_marker, 1)[0]

    compile(payload, "<runtime-reconciler-remote-cleanup>", "exec")
    assert "sep=chr(10)" in payload
    assert "p.write_text((sep.join(kept) + sep) if kept else '')" in payload


async def main() -> None:
    _assert_runtime_cleanup_payload_compiles()

    db = SessionLocal()
    original_transports = tunnel_managed._TRANSPORTS
    original_delete = tunnel_managed.core.delete_tunnel
    original_tp2027_phase = tunnel_managed._install_tp2027_phase

    try:
        # The orchestration smoke must stay deterministic and must not require
        # real SSH/TP2027 artifacts. Base transport behavior is mocked below.
        tunnel_managed._install_tp2027_phase = _skip_tp2027

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

        # ------------------------------------------------------------
        # Shared Iran -> two different Exit nodes.
        #
        # Two create-managed requests are launched concurrently. The per-Iran
        # provision lock must serialize the complete remote-mutation phase, and
        # the direct transport phase inside each request must also be serial.
        # ------------------------------------------------------------
        exit_two = _node(
            db,
            name="ci-managed-exit-two",
            node_type=NodeType.EXIT,
            ip="192.0.2.21",
        )
        exit_three = _node(
            db,
            name="ci-managed-exit-three",
            node_type=NodeType.EXIT,
            ip="192.0.2.22",
        )

        tracker = {
            "active": 0,
            "max_active": 0,
            "trace": [],
        }

        def tracked_success(name: str, latency: int):
            async def installer(tunnel_id: int, job_db):
                tracker["active"] += 1
                tracker["max_active"] = max(
                    int(tracker["max_active"]),
                    int(tracker["active"]),
                )
                tracker["trace"].append(
                    f"start:{tunnel_id}:{name}"
                )

                try:
                    # Make accidental overlap observable to the smoke test.
                    await asyncio.sleep(0.03)

                    row = (
                        job_db.query(TunnelTransport)
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
                    job_db.commit()

                    return {
                        "ok": True,
                        "transport": name,
                        "status": "online",
                    }
                finally:
                    tracker["trace"].append(
                        f"end:{tunnel_id}:{name}"
                    )
                    tracker["active"] -= 1

            return installer

        tunnel_managed._TRANSPORTS = (
            ("mtunnel", 90, tracked_success("mtunnel", 30)),
            ("backhaul", 100, tracked_success("backhaul", 34)),
            ("ssh_tun", 200, tracked_success("ssh_tun", 41)),
        )

        async def create_for_exit(exit_id: int):
            task_db = SessionLocal()
            try:
                return await tunnel_managed.create_managed_tunnel(
                    TunnelCreate(
                        iran_node_id=iran.id,
                        exit_node_id=exit_id,
                        priority=100,
                    ),
                    task_db,
                )
            finally:
                task_db.close()

        second_result, third_result = await asyncio.gather(
            create_for_exit(exit_two.id),
            create_for_exit(exit_three.id),
        )

        assert second_result["ok"] is True
        assert third_result["ok"] is True
        assert second_result["active_transport"] == "mtunnel"
        assert third_result["active_transport"] == "mtunnel"
        assert int(tracker["max_active"]) == 1, tracker["trace"]

        shared_iran_tunnels = (
            db.query(Tunnel)
            .filter(Tunnel.iran_node_id == iran.id)
            .order_by(Tunnel.id.asc())
            .all()
        )

        assert len(shared_iran_tunnels) == 3
        assert {
            int(item.exit_node_id)
            for item in shared_iran_tunnels
        } == {
            int(exit_node.id),
            int(exit_two.id),
            int(exit_three.id),
        }
        assert all(
            item.status.value == "online"
            for item in shared_iran_tunnels
        )

        # ------------------------------------------------------------
        # All direct paths fail -> rollback the newly-created logical tunnel.
        # ------------------------------------------------------------
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
        tunnel_managed._install_tp2027_phase = original_tp2027_phase
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
