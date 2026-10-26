from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import smart_transport_auto_v21 as smart
from ..database import get_db
from ..deps import require_admin
from ..models import Tunnel, TunnelPeerState, TunnelStatus, TunnelTransport
from ..smart_transport_auto_v21 import (
    CANDIDATE_STABLE_SECONDS,
    _smart_state,
    auto_block_reason,
)
from ..kernel_transport_registry_v209 import apply_kernel_transport_registry_v209

# API workers must expose the same additive candidate registry as the standalone
# transport-manager process. This fixes TP6 visibility and registers the V209
# IPIP/VXLAN lanes before catalog/state/install requests are served.
apply_kernel_transport_registry_v209()

from ..transport_candidates import (
    ACTIVE_SPECS,
    SPECS,
    catalog,
    install_transport,
    runtime,
    uninstall_transport,
)
from ..transport_candidates import spoof_wg
from ..transport_candidates.common import close_pair, connect_pair, tunnel_nodes

router = APIRouter(
    prefix="/v1/tunnels",
    tags=["tunnel-modern-transports"],
    dependencies=[Depends(require_admin)],
)


_PROFILE = {
    "tp27_fast": {
        "iran_profile": "tp27-auto-gre",
        "description": (
            "TP27 Fast full-L3: keyed native GRE first, then GRE/UDP FoU "
            "fallback with fail-closed health and throughput qualification."
        ),
    },
    "spoof_wg": {
        "iran_profile": "mutual-ip-spoof + wireguard-l3",
        "description": (
            "Spoof Tunnel v3.1 core carries a private WireGuard /30. "
            "Mutual spoof source addresses must be configured explicitly and "
            "the path is accepted only after TwinPanel full-L3 qualification."
        ),
    },
    "tp6_fast": {
        "iran_profile": "ipv6-carrier + private-ipv4-l3",
        "description": (
            "TP6 Fast uses real IPv6 as the outer carrier with keyed IP6GRE "
            "first and IPIP6 fallback. Explicit install only; no encryption."
        ),
    },
    "kernel_ipip": {
        "iran_profile": "native-ipip + private-ipv4-l3",
        "description": (
            "Linux kernel IPIP point-to-point L3 candidate. Low overhead and "
            "explicit install only; transport itself is not encrypted."
        ),
    },
    "kernel_vxlan": {
        "iran_profile": "native-vxlan-udp + private-ipv4-l3",
        "description": (
            "Linux kernel VXLAN over UDP point-to-point candidate with a "
            "dedicated VNI/port. Explicit install only; transport is unencrypted."
        ),
    },
    "kernel_gre": {
        "iran_profile": "direct-gre-retired",
        "description": "Retired migration fallback; removed after TP27 Fast promotion.",
    },
}


class SpoofWGConfiguration(BaseModel):
    iran_spoof_ip: str
    exit_spoof_ip: str


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _candidate_view(
    *,
    name: str,
    row: TunnelTransport | None,
    tunnel_id: int,
) -> dict:
    state = _smart_state(row) if row is not None else {}
    block = auto_block_reason(row) if row is not None else None

    stable_seconds = 0.0
    try:
        stable_seconds = max(
            0.0,
            float(state.get("stable_seconds") or 0.0),
        )
    except (TypeError, ValueError):
        stable_seconds = 0.0

    throughput = state.get("throughput")
    if not isinstance(throughput, dict):
        throughput = None

    benchmark_fresh = False
    benchmark_age = None
    if throughput is not None:
        try:
            measured = float(throughput.get("measured_at_epoch") or 0.0)
            if measured > 0:
                benchmark_age = max(0.0, time.time() - measured)
                benchmark_fresh = benchmark_age <= 1800.0
        except (TypeError, ValueError):
            pass

    online = bool(
        row is not None
        and bool(row.enabled)
        and _status(row.status) == "online"
    )

    qualified = bool(
        online
        and not block
        and stable_seconds >= float(CANDIDATE_STABLE_SECONDS)
    )

    extra: dict = {}
    if name == "spoof_wg":
        configuration = spoof_wg.configuration_for_view(
            row.config_text if row is not None else None
        )
        extra = {
            "configuration": configuration,
            "configured": bool(configuration.get("configured")),
            "configuration_required": not bool(configuration.get("configured")),
            "auto_install": False,
            "xdp": False,
            "upstream_version": spoof_wg.UPSTREAM_VERSION,
        }
    elif name in {"tp6_fast", "kernel_ipip", "kernel_vxlan"}:
        extra = {
            "auto_install": False,
            "configuration_required": False,
            "encrypted": False,
        }

    return {
        "runtime": runtime(name, tunnel_id),
        "enabled": bool(row.enabled) if row else False,
        "status": _status(row.status) if row else "not_installed",
        "latency_ms": row.latency_ms if row else None,
        "last_error": row.last_error if row else None,
        "last_healthy_at": (
            row.last_healthy_at.isoformat()
            if row and row.last_healthy_at
            else None
        ),
        "canary": True,
        "auto_managed": True,
        "qualified": qualified,
        "selectable": qualified,
        "stable_seconds": round(stable_seconds, 1),
        "required_stable_seconds": int(CANDIDATE_STABLE_SECONDS),
        "auto_block_reason": block,
        "quarantine_until_epoch": state.get("quarantine_until_epoch"),
        "benchmark": throughput,
        "benchmark_fresh": benchmark_fresh,
        "benchmark_age_seconds": (
            round(benchmark_age, 1)
            if benchmark_age is not None
            else None
        ),
        **extra,
        **_PROFILE.get(name, {}),
    }


def _compatibility_script(peer_ip: str) -> str:
    return f"""python3 - <<'PY'
import json
import os
import shutil
import socket
import subprocess

peer_ip = {peer_ip!r}


def run(command):
    try:
        proc = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=8,
            check=False,
        )
        return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except Exception as exc:
        return 99, "", f"{{type(exc).__name__}}:{{exc}}"


raw_socket = False
raw_socket_error = ""
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    sock.close()
    raw_socket = True
except Exception as exc:
    raw_socket_error = f"{{type(exc).__name__}}:{{exc}}"

route_rc, route_out, route_err = run(["ip", "-4", "route", "get", peer_ip])
ping_rc, ping_out, ping_err = run(["ping", "-c", "2", "-W", "2", peer_ip])

wg_tools = shutil.which("wg") is not None
tun_device = os.path.exists("/dev/net/tun")
wireguard_kernel = os.path.exists("/sys/module/wireguard")
if not wireguard_kernel and shutil.which("modprobe"):
    mod_rc, _, _ = run(["modprobe", "-n", "wireguard"])
    wireguard_kernel = mod_rc == 0

rp_filter_all = ""
try:
    rp_filter_all = open("/proc/sys/net/ipv4/conf/all/rp_filter", "r", encoding="utf-8").read().strip()
except Exception:
    pass

ip_forward = ""
try:
    ip_forward = open("/proc/sys/net/ipv4/ip_forward", "r", encoding="utf-8").read().strip()
except Exception:
    pass

input_policy = ""
if shutil.which("iptables"):
    _, out, _ = run(["iptables", "-S", "INPUT"])
    input_policy = (out.splitlines() or [""])[0]

payload = {{
    "raw_socket": raw_socket,
    "raw_socket_error": raw_socket_error,
    "tun_device": tun_device,
    "wg_tools": wg_tools,
    "wireguard_kernel": wireguard_kernel,
    "route_to_peer": route_rc == 0,
    "route_detail": route_out or route_err,
    "ping_peer": ping_rc == 0,
    "ping_detail": ping_out or ping_err,
    "rp_filter_all": rp_filter_all,
    "ip_forward": ip_forward,
    "input_policy": input_policy,
}}

print(json.dumps(payload, ensure_ascii=False))
PY"""


async def _node_compatibility(conn, peer_ip: str) -> dict:
    result = await conn.run(
        _compatibility_script(peer_ip),
        check=False,
        timeout=20,
    )
    if result.exit_status != 0:
        detail = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        raise RuntimeError(f"compatibility_probe_failed:{detail[-2500:]}")

    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("compatibility_probe_empty")

    try:
        payload = json.loads(lines[-1])
    except Exception as exc:
        raise RuntimeError(
            f"compatibility_probe_invalid_json:{lines[-1][-1200:]}"
        ) from exc

    if not isinstance(payload, dict):
        raise RuntimeError("compatibility_probe_invalid_payload")

    critical = {
        "raw_socket": bool(payload.get("raw_socket")),
        "tun_device": bool(payload.get("tun_device")),
        "wg_tools": bool(payload.get("wg_tools")),
        "wireguard_kernel": bool(payload.get("wireguard_kernel")),
        "route_to_peer": bool(payload.get("route_to_peer")),
    }

    payload["critical"] = critical
    payload["compatible"] = all(critical.values())
    return payload


async def _fresh_manual_candidate_health_v257(
    tunnel_id: int,
    name: str,
) -> dict:
    """Run the full candidate probe without accepting SmartAuto's 20s cache."""

    key = (int(tunnel_id), str(name).strip().lower())

    # The cache lookup in candidate_health_remote_v21 happens synchronously
    # before its first await. Removing this exact key immediately before calling
    # the active probe therefore guarantees that this cutover gate performs a
    # new service/interface + bidirectional L3 + egress probe.
    smart._candidate_health_cache.pop(key, None)

    probed_name, health = await smart.candidate_health_remote_v21(
        int(tunnel_id),
        str(name).strip().lower(),
        {},
    )

    if str(probed_name).strip().lower() != key[1]:
        return {
            "ok": False,
            "error": "manual_cutover_probe_transport_mismatch",
            "probed_transport": str(probed_name),
        }

    return dict(health or {})


def _peer_cutover_snapshot_v257(
    state: TunnelPeerState | None,
    *,
    node_id: int,
    started_at: datetime,
    name: str,
) -> dict:
    if state is None:
        return {
            "node_id": int(node_id),
            "fresh": False,
            "selected_transport": None,
            "endpoint_reachable": False,
            "tunnel_reachable": False,
            "last_error": "missing_report",
            "updated_at": None,
            "accepted": False,
        }

    updated_at = state.updated_at
    fresh = bool(updated_at is not None and updated_at >= started_at)
    selected = str(state.selected_transport or "").strip().lower()
    last_error = str(state.last_error or "").strip()

    accepted = bool(
        fresh
        and selected == name
        and bool(state.endpoint_reachable)
        and bool(state.tunnel_reachable)
        and not last_error
    )

    return {
        "node_id": int(node_id),
        "fresh": fresh,
        "selected_transport": selected or None,
        "endpoint_reachable": bool(state.endpoint_reachable),
        "tunnel_reachable": bool(state.tunnel_reachable),
        "last_error": last_error or None,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "accepted": accepted,
    }


async def _wait_manual_cutover_acceptance_v257(
    db: Session,
    tunnel: Tunnel,
    *,
    name: str,
    started_at: datetime,
    timeout_seconds: float = 30.0,
) -> tuple[bool, list[dict], str | None]:
    """Wait for post-reconcile Agent reports from both tunnel peers.

    Unified L3 V49 publishes service routes before it reports peer telemetry.
    Therefore two fresh healthy reports for the newly selected transport are the
    controller-side acknowledgement that both peer Agent convergence passes
    completed after this cutover, rather than stale pre-switch telemetry.
    """

    node_ids = (
        int(tunnel.iran_node_id),
        int(tunnel.exit_node_id),
    )
    deadline = asyncio.get_running_loop().time() + float(timeout_seconds)
    last_snapshot: list[dict] = []

    while True:
        db.expire_all()
        rows = {
            int(item.node_id): item
            for item in (
                db.query(TunnelPeerState)
                .filter(
                    TunnelPeerState.tunnel_id == int(tunnel.id),
                    TunnelPeerState.node_id.in_(node_ids),
                )
                .all()
            )
        }

        last_snapshot = [
            _peer_cutover_snapshot_v257(
                rows.get(node_id),
                node_id=node_id,
                started_at=started_at,
                name=name,
            )
            for node_id in node_ids
        ]

        if all(item["accepted"] for item in last_snapshot):
            return True, last_snapshot, None

        # A fresh report from the selected transport is authoritative negative
        # evidence. Do not wait out the whole timeout after an Agent has already
        # proved that the candidate carrier or service-route reconcile failed.
        for item in last_snapshot:
            if (
                item["fresh"]
                and item["selected_transport"] == name
                and not item["accepted"]
            ):
                reason = (
                    item.get("last_error")
                    or "manual_cutover_peer_not_reachable"
                )
                return False, last_snapshot, str(reason)[:900]

        if asyncio.get_running_loop().time() >= deadline:
            return False, last_snapshot, "manual_cutover_agent_confirmation_timeout"

        await asyncio.sleep(1.0)


def _rollback_manual_cutover_v257(
    db: Session,
    tunnel_id: int,
    previous: dict,
) -> Tunnel:
    db.rollback()
    db.expire_all()

    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("manual_cutover_rollback_tunnel_missing")

    tunnel.mode = previous["mode"]
    tunnel.active_transport = previous["active_transport"]
    tunnel.preferred_transport = previous["preferred_transport"]
    tunnel.status = previous["status"]
    tunnel.latency_ms = previous["latency_ms"]
    tunnel.last_switch_at = previous["last_switch_at"]
    db.commit()
    db.refresh(tunnel)
    return tunnel


@router.get("/transport-catalog")
def transport_catalog():
    return {
        "ok": True,
        "production_default": "manual",
        "promotion_policy": "health_then_speed",
        "download_weight": 0.70,
        "upload_weight": 0.30,
        "transports": [
            {
                **spec,
                **_PROFILE.get(str(spec["transport"]), {}),
                "auto_managed": True,
            }
            for spec in catalog()
        ],
    }


@router.get("/{tunnel_id}/modern-transports")
def list_modern_transports(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    tunnel = db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    rows = {
        str(row.transport): row
        for row in db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == tunnel_id,
            TunnelTransport.transport.in_(tuple(ACTIVE_SPECS)),
        )
        .all()
    }

    output = []
    for spec in catalog():
        name = str(spec["transport"])
        row = rows.get(name)
        output.append(
            {
                **spec,
                **_candidate_view(
                    name=name,
                    row=row,
                    tunnel_id=tunnel_id,
                ),
            }
        )

    return {
        "ok": True,
        "tunnel_id": tunnel_id,
        "mode": tunnel.mode,
        "active_transport": tunnel.active_transport,
        "preferred_transport": tunnel.preferred_transport,
        "production_default": "manual",
        "promotion_policy": "health_then_speed",
        "transports": output,
    }


@router.put("/{tunnel_id}/modern-transports/spoof_wg/config")
def configure_spoof_wg(
    tunnel_id: int,
    payload: SpoofWGConfiguration,
    db: Session = Depends(get_db),
):
    tunnel = db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    try:
        configuration = spoof_wg.validate_configuration(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == tunnel_id,
            TunnelTransport.transport == "spoof_wg",
        )
        .first()
    )

    if row is not None and _status(row.status) == "installing":
        raise HTTPException(
            status_code=409,
            detail="Spoof Tunnel installation is currently running",
        )
    if row is not None and bool(row.enabled) and _status(row.status) == "online":
        raise HTTPException(
            status_code=409,
            detail="Remove the online Spoof Tunnel before changing its spoof addresses",
        )

    if row is None:
        row = TunnelTransport(
            tunnel_id=tunnel_id,
            transport="spoof_wg",
            priority=int(ACTIVE_SPECS["spoof_wg"]["priority"]),
            enabled=False,
            status="not_installed",
        )
        db.add(row)
        db.flush()

    row.priority = int(ACTIVE_SPECS["spoof_wg"]["priority"])
    row.enabled = False
    row.status = "not_installed"
    row.latency_ms = None
    row.last_error = None
    row.config_text = spoof_wg.merge_configuration(
        row.config_text,
        configuration,
    )
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "tunnel_id": tunnel_id,
        "transport": "spoof_wg",
        "configuration": spoof_wg.configuration_for_view(row.config_text),
        "next": "install",
    }


@router.post("/{tunnel_id}/modern-transports/spoof_wg/compatibility-check")
async def check_spoof_wg_compatibility(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    tunnel = db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    try:
        _, iran, exit_node = tunnel_nodes(db, tunnel_id)
        _, core_sha256 = spoof_wg._artifact()
    except Exception as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Spoof compatibility prerequisites are incomplete",
                "error": str(exc)[:1200],
            },
        ) from exc

    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == tunnel_id,
            TunnelTransport.transport == "spoof_wg",
        )
        .first()
    )
    configured = bool(
        row is not None
        and spoof_wg.configuration_from_text(row.config_text) is not None
    )

    ci = ce = None
    try:
        ci, ce = await connect_pair(iran, exit_node, db)
        iran_result, exit_result = await asyncio.gather(
            _node_compatibility(ci, str(exit_node.public_ip)),
            _node_compatibility(ce, str(iran.public_ip)),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Server compatibility check failed",
                "error": str(exc)[:2500],
            },
        ) from exc
    finally:
        await close_pair(
            *[
                connection
                for connection in (ci, ce)
                if connection is not None
            ]
        )

    compatible = bool(
        iran_result.get("compatible")
        and exit_result.get("compatible")
    )

    blockers: list[str] = []
    for role, payload in (("iran", iran_result), ("exit", exit_result)):
        critical = payload.get("critical") or {}
        for key, passed in critical.items():
            if not passed:
                blockers.append(f"{role}:{key}")

    return {
        "ok": True,
        "tunnel_id": int(tunnel.id),
        "transport": "spoof_wg",
        "mode": tunnel.mode,
        "active_transport": tunnel.active_transport,
        "preferred_transport": tunnel.preferred_transport,
        "production_path_unchanged": True,
        "core": {
            "ok": True,
            "version": spoof_wg.UPSTREAM_VERSION,
            "sha256": core_sha256,
        },
        "iran": {
            "node_id": int(iran.id),
            "name": iran.name,
            "public_ip": iran.public_ip,
            **iran_result,
        },
        "exit": {
            "node_id": int(exit_node.id),
            "name": exit_node.name,
            "public_ip": exit_node.public_ip,
            **exit_result,
        },
        "compatible": compatible,
        "configured": configured,
        "ready_for_install": bool(compatible and configured),
        "blockers": blockers,
        "source_spoofing_verified": False,
        "limitation": (
            "This non-destructive check validates host/network prerequisites only. "
            "It does not forge source addresses and does not prove that the provider "
            "permits arbitrary source-IP spoofing."
        ),
    }


# TWINPANEL_MANUAL_MODERN_TRANSPORT_V192
# TWINPANEL_MANUAL_CUTOVER_ACCEPTANCE_V257
@router.post("/{tunnel_id}/modern-transports/{transport}/select-manual")
async def select_modern_transport_manual(
    tunnel_id: int,
    transport: str,
    db: Session = Depends(get_db),
):
    name = str(transport or "").strip().lower()
    if name not in ACTIVE_SPECS:
        raise HTTPException(
            status_code=404,
            detail="Unknown or retired modern transport",
        )

    tunnel = db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == tunnel_id,
            TunnelTransport.transport == name,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Transport not installed")

    if not bool(row.enabled):
        raise HTTPException(status_code=400, detail="Transport disabled")

    # Fast UI qualification remains useful, but it is never sufficient for a
    # production cutover. V257 always performs a brand-new full candidate probe
    # immediately before changing aggregate authority.
    view = _candidate_view(
        name=name,
        row=row,
        tunnel_id=tunnel_id,
    )
    if not bool(view.get("selectable")):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Transport is not qualified for manual production selection",
                "transport": name,
                "status": view.get("status"),
                "stable_seconds": view.get("stable_seconds"),
                "required_stable_seconds": view.get("required_stable_seconds"),
                "auto_block_reason": view.get("auto_block_reason"),
                "authority_unchanged": True,
            },
        )

    fresh_health = await _fresh_manual_candidate_health_v257(
        tunnel_id,
        name,
    )

    # candidate_health_remote_v21 writes authoritative member telemetry using
    # its own SessionLocal. Refresh this request session before evaluating the
    # just-probed row and before copying latency into aggregate state.
    db.expire_all()
    tunnel = db.get(Tunnel, tunnel_id)
    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == tunnel_id,
            TunnelTransport.transport == name,
        )
        .first()
    )
    if tunnel is None or row is None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Tunnel or transport changed during manual cutover preflight",
                "transport": name,
                "authority_unchanged": True,
            },
        )

    fresh_view = _candidate_view(
        name=name,
        row=row,
        tunnel_id=tunnel_id,
    )
    if (
        not bool(fresh_health.get("ok"))
        or not bool(fresh_view.get("selectable"))
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Fresh cutover probe rejected the transport; production authority was not changed",
                "transport": name,
                "authority_unchanged": True,
                "fresh_health": fresh_health,
                "status": fresh_view.get("status"),
                "stable_seconds": fresh_view.get("stable_seconds"),
                "required_stable_seconds": fresh_view.get("required_stable_seconds"),
                "auto_block_reason": fresh_view.get("auto_block_reason"),
            },
        )

    previous = {
        "mode": tunnel.mode,
        "active_transport": tunnel.active_transport,
        "preferred_transport": tunnel.preferred_transport,
        "status": tunnel.status,
        "latency_ms": tunnel.latency_ms,
        "last_switch_at": tunnel.last_switch_at,
    }

    cutover_started_at = datetime.utcnow()
    tunnel.mode = "manual"
    tunnel.active_transport = name
    tunnel.preferred_transport = name
    tunnel.status = TunnelStatus.ONLINE
    tunnel.latency_ms = row.latency_ms
    tunnel.last_switch_at = cutover_started_at

    db.commit()
    db.refresh(tunnel)

    accepted, peer_acceptance, acceptance_error = (
        await _wait_manual_cutover_acceptance_v257(
            db,
            tunnel,
            name=name,
            started_at=cutover_started_at,
        )
    )

    if not accepted:
        rolled_back = _rollback_manual_cutover_v257(
            db,
            tunnel_id,
            previous,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Manual transport cutover failed post-switch Data Plane acceptance and was rolled back",
                "transport": name,
                "rolled_back": True,
                "rollback_active_transport": rolled_back.active_transport,
                "rollback_preferred_transport": rolled_back.preferred_transport,
                "fresh_health": fresh_health,
                "peer_acceptance": peer_acceptance,
                "acceptance_error": acceptance_error,
            },
        )

    db.expire_all()
    tunnel = db.get(Tunnel, tunnel_id)
    assert tunnel is not None

    return {
        "ok": True,
        "tunnel_id": int(tunnel.id),
        "mode": tunnel.mode,
        "active_transport": tunnel.active_transport,
        "preferred_transport": tunnel.preferred_transport,
        "status": _status(tunnel.status),
        "latency_ms": tunnel.latency_ms,
        "transport": name,
        "fresh_probe": True,
        "dataplane_reconciled": True,
        "fresh_health": fresh_health,
        "peer_acceptance": peer_acceptance,
    }


@router.post("/{tunnel_id}/modern-transports/{transport}/install")
async def install_modern_transport(
    tunnel_id: int,
    transport: str,
    db: Session = Depends(get_db),
):
    name = str(transport or "").strip().lower()
    if name not in ACTIVE_SPECS:
        raise HTTPException(status_code=404, detail="Unknown or retired modern transport")

    tunnel = db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    if name == "spoof_wg":
        row = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == tunnel_id,
                TunnelTransport.transport == name,
            )
            .first()
        )
        if row is None or spoof_wg.configuration_from_text(row.config_text) is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Spoof Tunnel requires Iran and Exit spoof IPv4 addresses before install",
                    "transport": name,
                    "configuration_required": True,
                },
            )

    try:
        return await install_transport(name, tunnel_id, db)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"{ACTIVE_SPECS[name]['label']} canary failed",
                "transport": name,
                "error": str(exc)[:7000],
            },
        ) from exc


@router.delete("/{tunnel_id}/modern-transports/{transport}")
async def remove_modern_transport(
    tunnel_id: int,
    transport: str,
    db: Session = Depends(get_db),
):
    name = str(transport or "").strip().lower()
    if name not in SPECS and name not in {"gost_tun", "amneziawg", "netrix"}:
        raise HTTPException(status_code=404, detail="Unknown modern transport")

    if str(tunnel_id).strip() == "":
        raise HTTPException(status_code=400, detail="Invalid tunnel id")

    try:
        return await uninstall_transport(name, tunnel_id, db)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail={
                "message": f"{name} removal failed",
                "transport": name,
                "error": str(exc)[:4000],
            },
        ) from exc
