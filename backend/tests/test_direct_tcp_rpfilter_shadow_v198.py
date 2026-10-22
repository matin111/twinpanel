from __future__ import annotations

import asyncio
import inspect

from app import adaptive_candidate_qualification_v155 as qualification_v155
from app import direct_tcp_rpfilter_guard_v198 as guard_v198
from app import tunnel_transport_manager_v12 as manager_v12
from app.transport_candidates import common as candidate_common
from app.transport_candidates import tp27_tcp_direct


def test_direct_probe_sets_loose_rp_filter_before_v155_peer_probe() -> None:
    events: list[tuple] = []

    class Conn:
        def __init__(self, name: str) -> None:
            self.name = name

    iran = Conn("iran")
    exit_node = Conn("exit")

    async def fake_run(conn, script: str, label: str, timeout: int = 0) -> str:
        events.append(("run", conn.name, label, script, timeout))
        return ""

    async def fake_original(ci, ce, *, name: str, tunnel_id: int, rt: dict) -> dict:
        events.append(("probe", ci.name, ce.name, name, tunnel_id, rt["interface"]))
        return {"peer_ping": True, "packet_loss_pct": 0.0}

    old_run = candidate_common.run
    old_original = guard_v198._original_direct_peer_l3_probe

    try:
        candidate_common.run = fake_run
        guard_v198._original_direct_peer_l3_probe = fake_original

        result = asyncio.run(
            guard_v198.direct_peer_l3_probe_v198(
                iran,
                exit_node,
                name="tp27_tcp_direct",
                tunnel_id=6,
                rt={"interface": "tp27d6"},
            )
        )
    finally:
        candidate_common.run = old_run
        guard_v198._original_direct_peer_l3_probe = old_original

    assert result["peer_ping"] is True

    rp_events = [event for event in events if event[0] == "run"]
    assert len(rp_events) == 2
    assert {event[1] for event in rp_events} == {"iran", "exit"}
    assert {event[2] for event in rp_events} == {
        "direct_rp_filter_iran_v198",
        "direct_rp_filter_exit_v198",
    }
    for event in rp_events:
        assert "/proc/sys/net/ipv4/conf/tp27d6/rp_filter" in event[3]
        assert "net.ipv4.conf.tp27d6.rp_filter=2" in event[3]

    probe_index = next(i for i, event in enumerate(events) if event[0] == "probe")
    assert all(
        i < probe_index
        for i, event in enumerate(events)
        if event[0] == "run"
    )


def test_apply_guard_restores_both_direct_probe_authorities() -> None:
    old_applied = guard_v198._applied
    old_v155_probe = qualification_v155._direct_peer_l3_probe
    old_installer_probe = tp27_tcp_direct.probe

    try:
        guard_v198._applied = False
        guard_v198.apply_direct_tcp_rpfilter_guard_v198()

        assert (
            qualification_v155._direct_peer_l3_probe
            is guard_v198.direct_peer_l3_probe_v198
        )
        assert tp27_tcp_direct.probe is guard_v198.direct_peer_l3_probe_v198
    finally:
        guard_v198._applied = old_applied
        qualification_v155._direct_peer_l3_probe = old_v155_probe
        tp27_tcp_direct.probe = old_installer_probe


def test_manager_applies_guard_after_v155_shadowing_layer() -> None:
    source = inspect.getsource(manager_v12.main)

    v155_index = source.index("apply_adaptive_candidate_qualification_v155()")
    guard_index = source.index("apply_direct_tcp_rpfilter_guard_v198()")

    assert v155_index < guard_index
