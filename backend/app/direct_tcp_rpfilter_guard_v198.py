from __future__ import annotations

import asyncio
import shlex

from . import adaptive_candidate_qualification_v155 as qualification_v155
from .transport_candidates import common as candidate_common
from .transport_candidates import tp27_tcp_direct


# ============================================================
# TWINPANEL DIRECT TCP RPFILTER SHADOW GUARD V198
#
# Production evidence on Tunnel #6 showed that TP27 Direct TCP verified its
# outer TCP lanes but then failed peer /30 ping with 100% loss on every port.
# Candidate Dataplane V175 already relaxed rp_filter on candidate TUNs, but the
# manager applies Adaptive Candidate Qualification V155 afterwards. V155 then
# replaces tp27_tcp_direct.probe with its older peer-L3 probe, shadowing the
# V175 rp_filter protection.
#
# Keep the V155 qualification contract intact and restore only the missing
# dataplane precondition: set rp_filter=2 on the Direct TCP TUN on both nodes
# immediately before V155 runs peer-L3 qualification.
# ============================================================

MARKER = "TWINPANEL_DIRECT_TCP_RPFILTER_SHADOW_GUARD_V198"

_applied = False
_original_direct_peer_l3_probe = qualification_v155._direct_peer_l3_probe


async def _set_loose_rp_filter(conn, *, iface: str, label: str) -> None:
    key = f"net.ipv4.conf.{iface}.rp_filter=2"
    path = f"/proc/sys/net/ipv4/conf/{iface}/rp_filter"
    await candidate_common.run(
        conn,
        f"""
set -e
if [ -e {shlex.quote(path)} ]; then
  sysctl -w {shlex.quote(key)} >/dev/null
fi
""",
        label,
        20,
    )


async def direct_peer_l3_probe_v198(
    ci,
    ce,
    *,
    name: str,
    tunnel_id: int,
    rt: dict,
) -> dict:
    iface = str(rt["interface"])

    await asyncio.gather(
        _set_loose_rp_filter(
            ci,
            iface=iface,
            label="direct_rp_filter_iran_v198",
        ),
        _set_loose_rp_filter(
            ce,
            iface=iface,
            label="direct_rp_filter_exit_v198",
        ),
    )

    return await _original_direct_peer_l3_probe(
        ci,
        ce,
        name=name,
        tunnel_id=int(tunnel_id),
        rt=rt,
    )


def apply_direct_tcp_rpfilter_guard_v198() -> None:
    global _applied

    if _applied:
        return

    # _candidate_health_v155 resolves this module global at call time, while
    # the installer holds its own imported probe alias. Patch both authorities
    # after V155 is applied so neither path can bypass the rp_filter precondition.
    qualification_v155._direct_peer_l3_probe = direct_peer_l3_probe_v198
    tp27_tcp_direct.probe = direct_peer_l3_probe_v198

    _applied = True
    print(
        f"{MARKER}_ACTIVE "
        "scope=tp27_tcp_direct "
        "iran_rp_filter=2 exit_rp_filter=2 "
        "qualification=v155-preserved",
        flush=True,
    )
