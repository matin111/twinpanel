from __future__ import annotations

import asyncio
import contextvars
from typing import Any

from sqlalchemy.orm import Session

from . import tp27_self_repair_v265 as v265
from .transport_candidates.common import (
    parse_packet_loss_pct,
)


# ============================================================
# TWINPANEL TP27 UNDERLAY FAULT DOMAIN V306
#
# Production acceptance proved a pair-scoped failure mode which must not be
# treated as a broken TP27 carrier:
#
#   Iran A -> Exit X : severe asymmetric public-path loss
#   Iran A -> Exit Y : healthy at the same time
#
# In that situation both TP27 services/interfaces/addresses can be structurally
# correct. Rebuilding GRE/FoU cannot repair the provider/route between the two
# public endpoints, so destructive autonomous repair only creates extra churn.
#
# V306 is an additive policy overlay on V265/V304:
#   * keeps the existing carrier diagnosis authoritative;
#   * probes the public underlay only when the carrier is structurally present
#     but the inner peer path is unhealthy;
#   * classifies faults as structural_carrier, underlay_suspected,
#     underlay_pair or dataplane;
#   * promotes suspected public-path loss to underlay_pair only when another
#     TP27 pair on the same Iran node is concurrently healthy;
#   * suppresses MANAGER-initiated rebuild for corroborated underlay_pair only;
#   * leaves explicit panel/API repair and rebuild available to the operator;
#   * never marks the shared Iran Node globally offline;
#   * recommends replacing/rerouting only the affected logical pair.
#
# V303 FoU quarantine remains a separate candidate-ordering policy.
# ============================================================

MARKER = "TWINPANEL_TP27_UNDERLAY_FAULT_DOMAIN_V306"
VERSION = 306
UNDERLAY_PING_COUNT = 5
MAX_HEALTHY_UNDERLAY_PACKET_LOSS_PCT = 20.0

_applied = False

_pair_context: contextvars.ContextVar[
    dict[str, Any] | None
] = contextvars.ContextVar(
    "tp27_underlay_pair_context_v306",
    default=None,
)

_original_tunnel_nodes = v265.tunnel_nodes
_original_diagnose_with_connections = v265._diagnose_with_connections
_original_diagnosis_error = v265._diagnosis_error
_original_diagnosis_failure_kind = v265._diagnosis_failure_kind
_original_repair_tp27 = v265.repair_tp27
_original_diagnose_tp27 = v265.diagnose_tp27


def _tunnel_nodes(
    db: Session,
    tunnel_id: int,
):
    """Preserve the V265 helper contract while capturing this pair per task."""

    tunnel, iran, exit_node = _original_tunnel_nodes(
        db,
        int(tunnel_id),
    )

    healthy_sibling_tunnels = [
        int(row[0])
        for row in (
            db.query(v265.Tunnel.id)
            .join(
                v265.TunnelTransport,
                v265.TunnelTransport.tunnel_id == v265.Tunnel.id,
            )
            .filter(
                v265.Tunnel.id != int(tunnel.id),
                v265.Tunnel.iran_node_id == int(tunnel.iran_node_id),
                v265.Tunnel.is_active.is_(True),
                v265.TunnelTransport.transport == "tp27_fast",
                v265.TunnelTransport.enabled.is_(True),
                v265.TunnelTransport.status == "online",
                v265.TunnelTransport.last_error.is_(None),
            )
            .order_by(v265.Tunnel.id.asc())
            .all()
        )
    ]

    _pair_context.set(
        {
            "tunnel_id": int(tunnel.id),
            "iran_node_id": int(tunnel.iran_node_id),
            "exit_node_id": int(tunnel.exit_node_id),
            "iran_public": str(iran.public_ip),
            "exit_public": str(exit_node.public_ip),
            "healthy_sibling_tunnels": healthy_sibling_tunnels,
        }
    )

    return tunnel, iran, exit_node


async def _public_path_snapshot(
    conn,
    *,
    peer_public_ip: str,
) -> dict[str, Any]:
    result = await conn.run(
        (
            "LC_ALL=C ping "
            f"-c {UNDERLAY_PING_COUNT} "
            "-i 0.2 -W 1 "
            f"{peer_public_ip}"
        ),
        check=False,
        timeout=15,
    )

    text = str(result.stdout or "").strip()
    packet_loss = parse_packet_loss_pct(text)
    known = packet_loss is not None
    healthy = bool(
        known
        and float(packet_loss)
        <= MAX_HEALTHY_UNDERLAY_PACKET_LOSS_PCT
    )

    return {
        "peer_public_ip": str(peer_public_ip),
        "known": known,
        "healthy": healthy,
        "ping_exit_status": int(result.exit_status),
        "packet_loss_pct": packet_loss,
        "ping_summary": (
            text.splitlines()[-1]
            if text
            else ""
        ),
    }


def _structural_carrier_healthy(
    carrier: dict[str, Any],
) -> bool:
    for role in ("iran", "exit"):
        side = carrier.get(role)
        if not isinstance(side, dict):
            return False

        for key in (
            "service_active",
            "interface_present",
            "address_present",
        ):
            if not bool(side.get(key)):
                return False

    return True


def _carrier_fault_domain(
    carrier: dict[str, Any],
) -> str:
    if bool(carrier.get("healthy")):
        return "healthy"

    if not _structural_carrier_healthy(carrier):
        return "structural_carrier"

    underlay = carrier.get("underlay")
    if (
        isinstance(underlay, dict)
        and bool(underlay.get("degraded"))
    ):
        if bool(underlay.get("pair_corroborated")):
            return "underlay_pair"
        return "underlay_suspected"

    return "dataplane"


async def _diagnose_with_connections(
    ci,
    ce,
    rt: dict[str, Any],
) -> dict[str, Any]:
    """Enrich V265 carrier diagnosis with pair-scoped public-underlay truth."""

    carrier = dict(
        await _original_diagnose_with_connections(
            ci,
            ce,
            rt,
        )
    )

    # Healthy dataplane needs no additional public-path probe. This keeps the
    # normal healthy path just as cheap as V304.
    if bool(carrier.get("healthy")):
        carrier.update(
            {
                "fault_domain": "healthy",
                "repair_suppressed": False,
                "replacement_recommended": False,
                "underlay": {
                    "known": False,
                    "healthy": None,
                    "degraded": False,
                    "probe_skipped": "carrier_healthy",
                },
            }
        )
        return carrier

    # A missing service/interface/address is a real carrier problem. Public
    # route health does not own that failure and must not fence self-repair.
    if not _structural_carrier_healthy(carrier):
        carrier.update(
            {
                "fault_domain": "structural_carrier",
                "repair_suppressed": False,
                "replacement_recommended": False,
                "underlay": {
                    "known": False,
                    "healthy": None,
                    "degraded": False,
                    "probe_skipped": "structural_carrier_fault",
                },
            }
        )
        return carrier

    pair = _pair_context.get()
    if pair is None:
        carrier.update(
            {
                "fault_domain": "dataplane",
                "repair_suppressed": False,
                "replacement_recommended": False,
                "underlay": {
                    "known": False,
                    "healthy": None,
                    "degraded": False,
                    "probe_skipped": "pair_context_unavailable",
                },
            }
        )
        return carrier

    tunnel_id = int(pair["tunnel_id"])
    iran_public = str(pair["iran_public"])
    exit_public = str(pair["exit_public"])
    healthy_sibling_tunnels = [
        int(value)
        for value in pair.get("healthy_sibling_tunnels", [])
    ]

    iran_to_exit, exit_to_iran = await asyncio.gather(
        _public_path_snapshot(
            ci,
            peer_public_ip=exit_public,
        ),
        _public_path_snapshot(
            ce,
            peer_public_ip=iran_public,
        ),
    )

    known = bool(
        iran_to_exit["known"]
        and exit_to_iran["known"]
    )
    healthy = bool(
        known
        and iran_to_exit["healthy"]
        and exit_to_iran["healthy"]
    )
    degraded = bool(
        known
        and not healthy
    )
    pair_corroborated = bool(
        degraded
        and healthy_sibling_tunnels
    )

    underlay = {
        "version": VERSION,
        "scope": "pair",
        "tunnel_id": int(tunnel_id),
        "iran_public": iran_public,
        "exit_public": exit_public,
        "known": known,
        "healthy": healthy,
        "degraded": degraded,
        "pair_corroborated": pair_corroborated,
        "healthy_sibling_tunnels": healthy_sibling_tunnels,
        "max_healthy_packet_loss_pct": (
            MAX_HEALTHY_UNDERLAY_PACKET_LOSS_PCT
        ),
        "iran_to_exit": iran_to_exit,
        "exit_to_iran": exit_to_iran,
    }

    carrier["underlay"] = underlay
    carrier["fault_domain"] = (
        "underlay_pair"
        if pair_corroborated
        else (
            "underlay_suspected"
            if degraded
            else "dataplane"
        )
    )
    carrier["repair_suppressed"] = pair_corroborated
    carrier["replacement_recommended"] = pair_corroborated

    return carrier


def _diagnosis_error(
    diagnosis: dict[str, Any],
) -> str:
    carrier = diagnosis.get("carrier")
    if isinstance(carrier, dict):
        fault_domain = str(
            carrier.get("fault_domain")
            or _carrier_fault_domain(carrier)
        )

        if fault_domain == "underlay_pair":
            underlay = carrier.get("underlay")
            if not isinstance(underlay, dict):
                underlay = {}

            iran_to_exit = underlay.get(
                "iran_to_exit"
            )
            if not isinstance(
                iran_to_exit,
                dict,
            ):
                iran_to_exit = {}

            exit_to_iran = underlay.get(
                "exit_to_iran"
            )
            if not isinstance(
                exit_to_iran,
                dict,
            ):
                exit_to_iran = {}

            return (
                "tp27_underlay_degraded:"
                "scope=pair;"
                f"iran_to_exit_loss="
                f"{iran_to_exit.get('packet_loss_pct')};"
                f"exit_to_iran_loss="
                f"{exit_to_iran.get('packet_loss_pct')};"
                "carrier_rebuild=suppressed;"
                "replacement_recommended=true"
            )[:1800]

    return _original_diagnosis_error(
        diagnosis
    )


def _diagnosis_failure_kind(
    diagnosis: dict[str, Any],
) -> str:
    carrier = diagnosis.get("carrier")

    if isinstance(carrier, dict):
        fault_domain = str(
            carrier.get("fault_domain")
            or _carrier_fault_domain(carrier)
        )

        if fault_domain == "underlay_pair":
            return "underlay"

        if fault_domain == "structural_carrier":
            return "structural"

    return _original_diagnosis_failure_kind(
        diagnosis
    )


async def _manager_safe_repair_tp27(
    tunnel_id: int,
    db: Session,
    *,
    force_rebuild: bool = False,
    source: str = "api",
) -> dict[str, Any]:
    """Fence only destructive manager repair when the public pair is degraded."""

    normalized_source = str(
        source or "api"
    ).strip().lower()

    if normalized_source == "manager":
        diagnosis = await _original_diagnose_tp27(
            int(tunnel_id),
            db,
        )

        carrier = diagnosis.get("carrier")
        fault_domain = (
            str(
                carrier.get("fault_domain")
                or _carrier_fault_domain(
                    carrier
                )
            )
            if isinstance(carrier, dict)
            else ""
        )

        if fault_domain == "underlay_pair":
            # Avoid repeated destructive attempts every manager loop after the
            # threshold is reached. A fresh 8-cycle observation window is still
            # required before another manager-side suppression decision.
            v265._failure_cycles[
                int(tunnel_id)
            ] = 0

            underlay = (
                carrier.get("underlay")
                if isinstance(carrier, dict)
                else None
            )

            print(
                f"{MARKER}_UNDERLAY_DEGRADED "
                f"tunnel={int(tunnel_id)} "
                "repair=suppressed "
                "scope=pair "
                "replacement_recommended=true",
                flush=True,
            )

            return {
                "ok": False,
                "marker": MARKER,
                "version": VERSION,
                "tunnel_id": int(tunnel_id),
                "source": source,
                "changed": False,
                "suppressed": True,
                "reason": "underlay_pair_degraded",
                "fault_domain": "underlay_pair",
                "replacement_recommended": True,
                "underlay": underlay,
            }

    return await _original_repair_tp27(
        int(tunnel_id),
        db,
        force_rebuild=bool(
            force_rebuild
        ),
        source=str(
            source or "api"
        ),
    )


def apply_tp27_underlay_fault_domain_v306() -> None:
    global _applied
    if _applied:
        return

    # Only V265 module globals are patched. Existing API function objects keep
    # their public signatures, while their dynamic helper lookups gain V306
    # pair-health classification. Explicit panel repair remains operator-owned.
    v265.tunnel_nodes = _tunnel_nodes
    v265._diagnose_with_connections = _diagnose_with_connections
    v265._diagnosis_error = _diagnosis_error
    v265._diagnosis_failure_kind = _diagnosis_failure_kind
    v265.repair_tp27 = _manager_safe_repair_tp27

    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        f"underlay_ping_count={UNDERLAY_PING_COUNT} "
        f"max_underlay_loss="
        f"{MAX_HEALTHY_UNDERLAY_PACKET_LOSS_PCT:.1f}% "
        "fault_scope=pair "
        "manager_rebuild=underlay-suppressed "
        "explicit_api_repair=preserved",
        flush=True,
    )
