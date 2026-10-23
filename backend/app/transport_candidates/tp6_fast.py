from __future__ import annotations

import asyncio
import json

from sqlalchemy.orm import Session

from . import common
from .tp6_fast_contract import MTU, NAME, PROFILE_ORDER, TXQUEUELEN
from .tp6_fast_ipv6 import carrier_key, canonical_ipv6, discover_global_ipv6, peer_ipv6_route
from .tp6_fast_kernel import install_profile, reset_pair


# ============================================================
# TWINPANEL TP6 FAST CARRIER V207
#
# IPv6 is only the outer carrier. The inner TwinPanel L3 contract remains a
# private IPv4 /30, preserving existing VPN/account dataplanes. Profiles are
# kernel-only: keyed IP6GRE first, then IPIP6 fallback. IPv6 endpoints are
# discovered from each remote node's real route and installation fails closed.
# This module never changes active/preferred transport.
# ============================================================


async def install(tunnel_id: int, db: Session) -> dict:
    _, iran, exit_node = common.tunnel_nodes(db, tunnel_id)
    rt = common.runtime(NAME, tunnel_id)

    common.mark(
        db,
        tunnel_id,
        NAME,
        status="installing",
        meta=json.dumps(
            {
                **rt,
                "source": "linux-kernel",
                "outer_family": "ipv6",
                "profile_order": list(PROFILE_ORDER),
                "mtu": MTU,
                "txqueuelen": TXQUEUELEN,
                "ipv6_discovery": "automatic",
            },
            sort_keys=True,
        ),
    )

    ci = ce = None
    attempts: list[dict] = []

    try:
        ci, ce = await common.connect_pair(iran, exit_node, db)
        await asyncio.gather(common.prerequisites(ci), common.prerequisites(ce))

        iran_discovery, exit_discovery = await asyncio.gather(
            discover_global_ipv6(ci),
            discover_global_ipv6(ce),
        )
        iran_ipv6 = canonical_ipv6(str(iran_discovery["ipv6"]))
        exit_ipv6 = canonical_ipv6(str(exit_discovery["ipv6"]))

        iran_route, exit_route = await asyncio.gather(
            peer_ipv6_route(ci, exit_ipv6),
            peer_ipv6_route(ce, iran_ipv6),
        )
        key = carrier_key(tunnel_id, iran_ipv6, exit_ipv6)

        for profile in PROFILE_ORDER:
            try:
                await install_profile(
                    ci,
                    ce,
                    rt=rt,
                    iran_ipv6=iran_ipv6,
                    exit_ipv6=exit_ipv6,
                    carrier_key=key,
                    profile=profile,
                )
                health = await common.probe(
                    ci,
                    ce,
                    name=NAME,
                    tunnel_id=tunnel_id,
                    rt=rt,
                )
                attempts.append({"profile": profile, "result": "online"})

                meta = {
                    **rt,
                    **health,
                    "source": "linux-kernel",
                    "outer_family": "ipv6",
                    "selected_profile": profile,
                    "profile_order": list(PROFILE_ORDER),
                    "iran_ipv6": iran_ipv6,
                    "exit_ipv6": exit_ipv6,
                    "iran_ipv6_preflight": iran_route,
                    "exit_ipv6_preflight": exit_route,
                    "carrier_key": key,
                    "mtu": MTU,
                    "txqueuelen": TXQUEUELEN,
                    "attempts": attempts,
                }
                common.mark(
                    db,
                    tunnel_id,
                    NAME,
                    status="online",
                    latency_ms=health["latency_ms"],
                    meta=json.dumps(meta, ensure_ascii=False, sort_keys=True),
                )
                return {
                    "ok": True,
                    "transport": NAME,
                    "runtime": rt,
                    "profile": profile,
                    "outer": {
                        "family": "ipv6",
                        "iran_ipv6": iran_ipv6,
                        "exit_ipv6": exit_ipv6,
                    },
                    "probe": health,
                }
            except Exception as exc:
                attempts.append(
                    {
                        "profile": profile,
                        "result": "failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        await reset_pair(ci, ce, rt)
        raise RuntimeError(f"tp6_all_profiles_failed:{attempts!r}")

    except Exception as exc:
        a = await common.diag(ci, rt["iran_service"], rt["interface"]) if ci else ""
        b = await common.diag(ce, rt["exit_service"], rt["interface"]) if ce else ""
        msg = (
            f"{type(exc).__name__}: {exc} | "
            f"iran={a[-1800:]} | exit={b[-1800:]}"
        )
        common.mark(db, tunnel_id, NAME, status="failed", error=msg)
        raise RuntimeError(msg) from exc
    finally:
        await common.close_pair(ci, ce)
