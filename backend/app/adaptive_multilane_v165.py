from __future__ import annotations

from . import smart_transport_auto_v21 as smart
from . import tp27_reference_runtime_v91 as reference_v91
from . import transport_candidates as candidates
from .transport_candidates import common as candidate_common
from .transport_candidates import tp27_mieru_tcp


# ============================================================
# TWINPANEL ADAPTIVE MULTI-LANE V165
#
# Registers TP27 Mieru TCP as a fourth independent L3 carrier without changing
# the existing Direct TCP/MASQUE implementations. SmartAuto remains the sole
# authority for install, health qualification, benchmark and promotion.
# ============================================================

MARKER = "TWINPANEL_ADAPTIVE_MULTILANE_V165"
NAME = "tp27_mieru_tcp"
SPEC = {
    "priority": 115,
    "label": "TP27 Mieru TCP",
    "family": "tp27-mieru-tcp-l3",
}

_applied = False
_previous_v91_policy = None
_base_runtime = candidates.runtime
_base_policy_ids = candidates.policy_ids
_base_uninstall = candidates.uninstall_transport


def _runtime(tunnel_id: int) -> dict:
    tid = max(int(tunnel_id), 1)
    slot = tid % 16384
    base = slot * 4
    third = (base // 256) & 0xFF
    fourth = base % 256
    iran_ip = f"10.252.{third}.{fourth + 1}"
    exit_ip = f"10.252.{third}.{fourth + 2}"
    return {
        "transport": NAME,
        "interface": f"tp27r{tid}"[:15],
        "network": f"10.252.{third}.{fourth}/30",
        "iran_ip": iran_ip,
        "exit_ip": exit_ip,
        "iran_addr": f"{iran_ip}/30",
        "exit_addr": f"{exit_ip}/30",
        "port": 38200 + (tid % 500),
        "iran_service": f"twinpanel-{NAME}-{tid}-iran.service",
        "exit_service": f"twinpanel-{NAME}-{tid}-exit.service",
        "priority": int(SPEC["priority"]),
    }


def runtime(name: str, tunnel_id: int) -> dict:
    value = str(name or "").strip().lower()
    if value == NAME:
        return _runtime(tunnel_id)
    return _base_runtime(value, tunnel_id)


def policy_ids(name: str, tunnel_id: int) -> tuple[int, int]:
    value = str(name or "").strip().lower()
    if value == NAME:
        table = 32000 + (int(tunnel_id) % 900)
        return table, table
    return _base_policy_ids(value, tunnel_id)


async def uninstall_transport(name: str, tunnel_id: int, db):
    value = str(name or "").strip().lower()
    if value != NAME:
        return await _base_uninstall(value, tunnel_id, db)

    _, iran, exit_node = candidate_common.tunnel_nodes(db, tunnel_id)
    rt = _runtime(tunnel_id)
    rt["tunnel_id"] = int(tunnel_id)
    ci = ce = None
    try:
        ci, ce = await candidate_common.connect_pair(iran, exit_node, db)
        await tp27_mieru_tcp._reset_pair(
            ci,
            ce,
            rt,
            str(iran.public_ip),
        )
        table, priority = policy_ids(NAME, tunnel_id)
        await ci.run(
            f"set +e; ip rule del priority {priority} 2>/dev/null || true; "
            f"ip route flush table {table} 2>/dev/null || true; "
            f"rm -rf /etc/twinpanel/mieru-tcp/tunnel-{int(tunnel_id)}; true",
            check=False,
        )
        await ce.run(
            f"set +e; rm -rf /etc/twinpanel/mieru-tcp/tunnel-{int(tunnel_id)}; true",
            check=False,
        )
        candidate_common.mark(
            db,
            tunnel_id,
            NAME,
            status="not_installed",
            enabled=False,
            error=None,
            latency_ms=None,
        )
        return {"ok": True, "transport": NAME, "removed": True}
    finally:
        await candidate_common.close_pair(ci, ce)


def _apply_lane_policy() -> None:
    if _previous_v91_policy is not None:
        _previous_v91_policy()
    smart.AUTO_INSTALL_NAMES = (
        "tp27_fast",
        "tp27_masque",
        NAME,
        "tp27_tcp_direct",
    )


def apply_adaptive_multilane_v165() -> None:
    global _applied, _previous_v91_policy
    if _applied:
        return

    candidate_common.SPECS[NAME] = SPEC
    candidates.SPECS[NAME] = SPEC
    candidates.ACTIVE_SPECS[NAME] = SPEC
    candidates.INSTALLERS[NAME] = tp27_mieru_tcp.install

    candidates.runtime = runtime
    candidates.policy_ids = policy_ids
    candidates.uninstall_transport = uninstall_transport
    candidate_common.runtime = runtime
    candidate_common.policy_ids = policy_ids
    tp27_mieru_tcp.runtime = runtime

    smart.candidate_runtime = runtime
    smart.CANDIDATE_NAMES = frozenset(set(smart.CANDIDATE_NAMES) | {NAME})
    smart.ALL_AUTO_NAMES = frozenset(
        smart.BASE_MODERN_NAMES | smart.CANDIDATE_NAMES | smart.LEGACY_NAMES
    )

    expected = {
        "tp27_fast",
        "tp27_masque",
        NAME,
        "tp27_tcp_direct",
    }
    missing = sorted(expected - set(smart.CANDIDATE_NAMES))
    if missing:
        raise RuntimeError(
            "adaptive_multilane_v165_candidates_missing:"
            + ",".join(missing)
        )

    _previous_v91_policy = reference_v91.activate_manager_candidate_policy_v91
    _apply_lane_policy()
    reference_v91.activate_manager_candidate_policy_v91 = _apply_lane_policy

    _applied = True
    print(
        f"{MARKER}_ACTIVE "
        "lanes=tp27_fast,tp27_masque,tp27_mieru_tcp,tp27_tcp_direct "
        "mieru=tcp+socks5+l3 "
        "existing_candidates=unchanged "
        "failover=smartauto-v21",
        flush=True,
    )
