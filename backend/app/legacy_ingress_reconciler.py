from __future__ import annotations

import asyncio

from .database import SessionLocal
from .models import Node, NodeType, Tunnel
from .routers.provision import ssh_connect_saved


# ============================================================
# TWINPANEL LEGACY INGRESS RECONCILER V1
#
# Modern Agent routing uses the shared authoritative chains:
#   TP_DNAT, TP_SNAT, TP_EGRESS, TP_FWD, TP_EGRESS_FWD, TP_CISCO_MSS
#
# Older emergency/manual builds created per-tunnel chains such as:
#   TP_PUBLIC_<id>, TP_FORWARD_<id>, TP_SNAT_<id>
#
# Those stale chains can leave duplicate public-port DNAT rules behind when
# one Iran node fans out to several Exit nodes. This reconciler removes only
# the legacy suffixed chain namespace and never touches the modern chains.
# ============================================================

INITIAL_DELAY_SECONDS = 90
INTERVAL_SECONDS = 1800


def _active_iran_nodes(db) -> list[Node]:
    iran_ids = {
        int(row[0])
        for row in (
            db.query(Tunnel.iran_node_id)
            .filter(Tunnel.is_active.is_(True))
            .distinct()
            .all()
        )
    }

    if not iran_ids:
        return []

    return (
        db.query(Node)
        .filter(
            Node.id.in_(sorted(iran_ids)),
            Node.node_type == NodeType.IRAN,
            Node.retired_at.is_(None),
        )
        .order_by(Node.id.asc())
        .all()
    )


async def _reconcile_node(node: Node, db) -> dict:
    conn = await ssh_connect_saved(node, db)

    try:
        result = await conn.run(
            r"""
set -eu

removed=""

for chain in $(iptables -t nat -S 2>/dev/null | awk '/^-N TP_PUBLIC_[0-9]+$/ {print $2}'); do
    while iptables -t nat -C PREROUTING -j "$chain" >/dev/null 2>&1; do
        iptables -t nat -D PREROUTING -j "$chain" >/dev/null 2>&1 || break
    done
    iptables -t nat -F "$chain" >/dev/null 2>&1 || true
    iptables -t nat -X "$chain" >/dev/null 2>&1 || true
    removed="$removed $chain"
done

for chain in $(iptables -t filter -S 2>/dev/null | awk '/^-N TP_FORWARD_[0-9]+$/ {print $2}'); do
    while iptables -t filter -C FORWARD -j "$chain" >/dev/null 2>&1; do
        iptables -t filter -D FORWARD -j "$chain" >/dev/null 2>&1 || break
    done
    iptables -t filter -F "$chain" >/dev/null 2>&1 || true
    iptables -t filter -X "$chain" >/dev/null 2>&1 || true
    removed="$removed $chain"
done

for chain in $(iptables -t nat -S 2>/dev/null | awk '/^-N TP_SNAT_[0-9]+$/ {print $2}'); do
    while iptables -t nat -C POSTROUTING -j "$chain" >/dev/null 2>&1; do
        iptables -t nat -D POSTROUTING -j "$chain" >/dev/null 2>&1 || break
    done
    iptables -t nat -F "$chain" >/dev/null 2>&1 || true
    iptables -t nat -X "$chain" >/dev/null 2>&1 || true
    removed="$removed $chain"
done

# Fail closed if any legacy chain still remains.
if iptables -t nat -S 2>/dev/null | grep -qE '^-N TP_(PUBLIC|SNAT)_[0-9]+$'; then
    echo "legacy_nat_chain_still_exists"
    exit 71
fi

if iptables -t filter -S 2>/dev/null | grep -qE '^-N TP_FORWARD_[0-9]+$'; then
    echo "legacy_filter_chain_still_exists"
    exit 72
fi

printf 'REMOVED=%s\n' "${removed# }"
""",
            check=False,
            timeout=60,
        )

        if result.exit_status != 0:
            text = result.stderr or result.stdout or f"exit={result.exit_status}"
            raise RuntimeError(str(text)[-2500:])

        detail = str(result.stdout or "").strip()

        if detail and detail != "REMOVED=":
            print(
                f"[LegacyIngressReconciler] node={int(node.id)} {detail}",
                flush=True,
            )

        return {
            "node_id": int(node.id),
            "detail": detail,
        }

    finally:
        conn.close()
        await conn.wait_closed()


async def reconcile_once() -> dict:
    db = SessionLocal()

    try:
        nodes = _active_iran_nodes(db)
        results = []
        errors: dict[int, str] = {}

        for node in nodes:
            try:
                results.append(
                    await _reconcile_node(node, db)
                )
            except Exception as exc:
                errors[int(node.id)] = str(exc)[:2500]
                print(
                    f"[LegacyIngressReconciler] ERROR node={int(node.id)} "
                    f"error={errors[int(node.id)]!r}",
                    flush=True,
                )

        return {
            "results": results,
            "errors": errors,
        }

    finally:
        db.close()


async def reconciler_loop() -> None:
    print(
        "TWINPANEL_LEGACY_INGRESS_RECONCILER_START "
        f"interval={INTERVAL_SECONDS}s",
        flush=True,
    )

    await asyncio.sleep(INITIAL_DELAY_SECONDS)

    while True:
        try:
            await reconcile_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                f"[LegacyIngressReconciler] CYCLE_ERROR error={exc!r}",
                flush=True,
            )

        await asyncio.sleep(INTERVAL_SECONDS)
