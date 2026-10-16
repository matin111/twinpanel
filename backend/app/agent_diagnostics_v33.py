from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

from redis import Redis
from sqlalchemy.orm import Session

from .config import settings
from .models import Node, Tunnel, TunnelTransport
from .mtunnel_transport import mtunnel_runtime_values
from .tp2027_provision import backhaul_runtime_values, tp2027_runtime_values
from .transport_candidates.common import runtime as modern_runtime


V33_TRANSPORTS = (
    "kcp_2027",
    "mtunnel",
    "kernel_gre",
    "gost_tun",
)

CACHE_TTL_SECONDS = 120
AGENT_VERSION = "v33.1"


def _cache_key(tunnel_id: int, node_id: int) -> str:
    return f"twinpanel:v33:diag:{int(tunnel_id)}:{int(node_id)}"


def _redis() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def save_agent_report(
    tunnel_id: int,
    node_id: int,
    *,
    agent_version: str,
    diagnostics: dict[str, Any],
) -> None:
    payload = {
        "tunnel_id": int(tunnel_id),
        "node_id": int(node_id),
        "agent_version": str(agent_version or "unknown")[:64],
        "reported_at": time.time(),
        "diagnostics": diagnostics,
    }
    client = _redis()
    try:
        client.setex(
            _cache_key(tunnel_id, node_id),
            CACHE_TTL_SECONDS,
            json.dumps(payload, separators=(",", ":")),
        )
    finally:
        client.close()


def load_agent_report(tunnel_id: int, node_id: int) -> dict[str, Any] | None:
    client = _redis()
    try:
        raw = client.get(_cache_key(tunnel_id, node_id))
    finally:
        client.close()

    if not raw:
        return None

    try:
        payload = json.loads(raw)
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    return payload


def _db_row(db: Session, tunnel_id: int, name: str) -> dict[str, Any]:
    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == name,
        )
        .first()
    )

    if row is None:
        return {
            "present": False,
            "enabled": False,
            "status": "not_installed",
            "latency_ms": None,
            "last_error": None,
        }

    return {
        "present": True,
        "enabled": bool(row.enabled),
        "status": str(row.status or ""),
        "latency_ms": row.latency_ms,
        "last_error": row.last_error,
        "last_healthy_at": row.last_healthy_at.isoformat() if row.last_healthy_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def runtime_for(name: str, tunnel_id: int) -> dict[str, Any]:
    if name == "kcp_2027":
        rt = dict(tp2027_runtime_values(name, tunnel_id))
        rt["carrier"] = dict(backhaul_runtime_values(tunnel_id))
        rt["secret_kind"] = "file"
        rt["secret_path"] = f"/etc/twinpanel/backhaul/{rt['interface']}.key"
        rt["server_role"] = "exit"
        rt["firewall_marker"] = f"TP2027-BH{int(tunnel_id)}-udp-{int(rt['port'])}"
        return rt

    if name == "mtunnel":
        rt = dict(mtunnel_runtime_values(tunnel_id))
        rt["iran_service"] = rt["service"]
        rt["exit_service"] = rt["service"]
        rt["protocol"] = "udp"
        rt["server_role"] = "exit"
        rt["secret_kind"] = "mtunnel_config"
        rt["secret_path"] = rt["config"]
        rt["firewall_marker"] = str(int(rt["port"]))
        return rt

    rt = dict(modern_runtime(name, tunnel_id))
    if name == "kernel_gre":
        rt["protocol"] = "gre"
        rt["server_role"] = None
        rt["firewall_marker"] = f"TwinPanel-GRE-{int(tunnel_id)}"
    elif name == "gost_tun":
        rt["protocol"] = "tcp"
        rt["server_role"] = "exit"
        rt["firewall_marker"] = f"TwinPanel-GOST-{int(tunnel_id)}"
    return rt


def desired_targets_for_node(node_id: int, db: Session) -> list[dict[str, Any]]:
    node = db.get(Node, int(node_id))
    if node is None or getattr(node, "retired_at", None) is not None:
        return []

    tunnels = (
        db.query(Tunnel)
        .filter(
            Tunnel.is_active.is_(True),
            (Tunnel.iran_node_id == int(node_id))
            | (Tunnel.exit_node_id == int(node_id)),
        )
        .order_by(Tunnel.priority.asc(), Tunnel.id.asc())
        .all()
    )

    output: list[dict[str, Any]] = []

    for tunnel in tunnels:
        iran = db.get(Node, int(tunnel.iran_node_id))
        exit_node = db.get(Node, int(tunnel.exit_node_id))
        if iran is None or exit_node is None:
            continue

        is_iran = int(node_id) == int(tunnel.iran_node_id)
        peer = exit_node if is_iran else iran
        targets: list[dict[str, Any]] = []

        for name in V33_TRANSPORTS:
            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == int(tunnel.id),
                    TunnelTransport.transport == name,
                )
                .first()
            )
            if row is None:
                continue

            rt = runtime_for(name, int(tunnel.id))
            carrier = rt.get("carrier") or {}
            server_role = str(rt.get("server_role") or "")

            targets.append(
                {
                    "transport": name,
                    "enabled": bool(row.enabled),
                    "db_status": str(row.status or ""),
                    "service": str(
                        rt.get("iran_service")
                        if is_iran
                        else rt.get("exit_service")
                        or rt.get("service")
                        or ""
                    ),
                    "interface": str(rt.get("interface") or ""),
                    "source_ip": str(rt.get("iran_ip") if is_iran else rt.get("exit_ip") or ""),
                    "peer_ip": str(rt.get("exit_ip") if is_iran else rt.get("iran_ip") or ""),
                    "remote_public_ip": str(peer.public_ip or ""),
                    "protocol": str(rt.get("protocol") or ""),
                    "port": int(rt["port"]) if rt.get("port") is not None else None,
                    "server": server_role == ("iran" if is_iran else "exit"),
                    "firewall_marker": rt.get("firewall_marker"),
                    "carrier_interface": carrier.get("interface"),
                    "secret_kind": rt.get("secret_kind"),
                    "secret_path": rt.get("secret_path"),
                }
            )

        output.append(
            {
                "tunnel_id": int(tunnel.id),
                "node_id": int(node_id),
                "node_role": "iran" if is_iran else "exit",
                "peer_node_id": int(peer.id),
                "targets": targets,
            }
        )

    return output


def _service_active(side: dict[str, Any]) -> bool:
    return str(((side.get("service") or {}).get("ActiveState") or "")).lower() == "active"


def _iface_exists(side: dict[str, Any]) -> bool:
    return bool(((side.get("interface") or {}).get("exists")))


def _listener_ok(side: dict[str, Any]) -> bool:
    listener = side.get("listener") or {}
    return (not listener.get("required")) or bool(listener.get("present"))


def _ping_ok(side: dict[str, Any]) -> bool:
    ping = side.get("ping") or {}
    try:
        return int(ping.get("received") or 0) > 0 and float(ping.get("loss_pct") or 100.0) < 100.0
    except Exception:
        return False


def _secret_match(iran: dict[str, Any], exit_side: dict[str, Any]) -> bool | None:
    left = iran.get("secret") or {}
    right = exit_side.get("secret") or {}
    if not left.get("checked") and not right.get("checked"):
        return None
    if not left.get("present") or not right.get("present"):
        return False
    return bool(left.get("sha256") and left.get("sha256") == right.get("sha256"))


def _classify(
    name: str,
    iran: dict[str, Any],
    exit_side: dict[str, Any],
    secret_match: bool | None,
) -> tuple[str, str]:
    if not iran.get("ok") or not exit_side.get("ok"):
        return "agent_diagnostic_error", "At least one node agent could not complete the local diagnostic."
    if not _service_active(iran) or not _service_active(exit_side):
        return "service_down", "At least one transport service is not active."
    if not _iface_exists(iran) or not _iface_exists(exit_side):
        return "interface_missing", "At least one transport interface is missing."
    if not _listener_ok(exit_side):
        return "listener_missing", "The expected Exit-side listener is not present."
    fw = exit_side.get("firewall") or {}
    if fw.get("checked") and fw.get("present") is False:
        return "firewall_rule_missing", "The transport-specific inbound firewall rule is missing."
    if secret_match is False:
        return "secret_mismatch", "Peer key material is missing or does not match."

    iran_ok = _ping_ok(iran)
    exit_ok = _ping_ok(exit_side)
    if iran_ok and exit_ok:
        return "healthy", "Bidirectional peer L3 is healthy."
    if iran_ok != exit_ok:
        return "one_way_peer_loss", "Peer L3 works in only one direction."
    if name == "kcp_2027":
        return "kcp_dataplane_stalled", "KCP local runtime checks pass, but peer L3 remains at 100% loss."
    if name == "mtunnel":
        return "mtunnel_udp_dataplane_stalled", "MTunnel local runtime checks pass, but UDP-backed peer L3 remains at 100% loss."
    if name == "kernel_gre":
        return "gre_dataplane_blocked", "GRE interfaces exist on both nodes, but protocol-47 peer L3 remains unavailable."
    if name == "gost_tun":
        return "gost_dataplane_stalled", "GOST local runtime checks pass, but TUN peer L3 remains unavailable."
    return "peer_l3_loss", "Peer L3 remains unavailable."


def _public_side(side: dict[str, Any]) -> dict[str, Any]:
    output = dict(side or {})
    secret = dict(output.get("secret") or {})
    secret.pop("sha256", None)
    if secret:
        output["secret"] = secret
    return output


def build_agent_diagnosis(tunnel_id: int, db: Session) -> dict[str, Any]:
    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")

    iran_id = int(tunnel.iran_node_id)
    exit_id = int(tunnel.exit_node_id)
    iran_report = load_agent_report(tunnel_id, iran_id)
    exit_report = load_agent_report(tunnel_id, exit_id)

    now = time.time()

    def agent_meta(report: dict[str, Any] | None) -> dict[str, Any]:
        if not report:
            return {
                "available": False,
                "agent_version": None,
                "age_seconds": None,
            }
        reported_at = float(report.get("reported_at") or 0.0)
        return {
            "available": True,
            "agent_version": report.get("agent_version"),
            "age_seconds": max(0, int(now - reported_at)) if reported_at else None,
        }

    output: list[dict[str, Any]] = []

    for name in V33_TRANSPORTS:
        row = _db_row(db, int(tunnel_id), name)
        if not row.get("present"):
            continue

        rt = runtime_for(name, int(tunnel_id))
        carrier = rt.get("carrier") or {}
        iran_diag = ((iran_report or {}).get("diagnostics") or {}).get(name)
        exit_diag = ((exit_report or {}).get("diagnostics") or {}).get(name)

        if not isinstance(iran_diag, dict) or not isinstance(exit_diag, dict):
            missing = []
            if not isinstance(iran_diag, dict):
                missing.append("iran")
            if not isinstance(exit_diag, dict):
                missing.append("exit")
            item = {
                "transport": name,
                "db": row,
                "runtime": {
                    "interface": rt.get("interface"),
                    "iran_ip": rt.get("iran_ip"),
                    "exit_ip": rt.get("exit_ip"),
                    "port": rt.get("port"),
                    "protocol": rt.get("protocol"),
                    "carrier_interface": carrier.get("interface"),
                },
                "root_cause_code": "agent_unavailable",
                "summary": "Fresh diagnostics are not available from: " + ", ".join(missing),
                "secret_match": None,
                "iran": _public_side(iran_diag or {"ok": False, "error": "agent_unavailable"}),
                "exit": _public_side(exit_diag or {"ok": False, "error": "agent_unavailable"}),
            }
            output.append(item)
            continue

        secret_match = _secret_match(iran_diag, exit_diag)
        code, summary = _classify(name, iran_diag, exit_diag, secret_match)
        output.append(
            {
                "transport": name,
                "db": row,
                "runtime": {
                    "interface": rt.get("interface"),
                    "iran_ip": rt.get("iran_ip"),
                    "exit_ip": rt.get("exit_ip"),
                    "port": rt.get("port"),
                    "protocol": rt.get("protocol"),
                    "carrier_interface": carrier.get("interface"),
                },
                "root_cause_code": code,
                "summary": summary,
                "secret_match": secret_match,
                "iran": _public_side(iran_diag),
                "exit": _public_side(exit_diag),
            }
        )

    unhealthy = [
        item["transport"]
        for item in output
        if item.get("root_cause_code") != "healthy"
    ]

    return {
        "ok": True,
        "read_only": True,
        "source": "node_agents",
        "tunnel_id": int(tunnel_id),
        "active_transport": tunnel.active_transport,
        "preferred_transport": tunnel.preferred_transport,
        "transports": output,
        "unhealthy": unhealthy,
        "agents": {
            "iran": agent_meta(iran_report),
            "exit": agent_meta(exit_report),
        },
        "partial": not bool(iran_report and exit_report),
        "marker": "TWINPANEL_AGENT_FIRST_DEEP_DIAGNOSTICS_V33_ACTIVE",
    }


def render_agent(node_id: int, api_base: str) -> str:
    template_path = Path(__file__).with_name("twinpanel_diag_agent.py.tpl")
    template = template_path.read_text(encoding="utf-8")
    return (
        template.replace("__API_LITERAL__", repr(str(api_base).rstrip("/")))
        .replace("__NODE_ID__", str(int(node_id)))
        .replace("__SECRET_LITERAL__", repr(settings.node_agent_shared_secret))
    )


async def install_agent_on_connection(conn, node_id: int, api_base: str) -> dict[str, Any]:
    source = render_agent(node_id, api_base)
    encoded = base64.b64encode(source.encode("utf-8")).decode("ascii")
    unit = """[Unit]\nDescription=TwinPanel Diagnostics Agent V33\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nExecStart=/usr/bin/python3 /opt/twinpanel-diagnostics-agent/agent.py\nRestart=always\nRestartSec=3\nEnvironment=PYTHONUNBUFFERED=1\n\n[Install]\nWantedBy=multi-user.target\n"""
    unit_encoded = base64.b64encode(unit.encode("utf-8")).decode("ascii")

    command = (
        "set -e; "
        "mkdir -p /opt/twinpanel-diagnostics-agent; "
        f"echo {encoded} | base64 -d > /opt/twinpanel-diagnostics-agent/agent.py; "
        "chmod 0755 /opt/twinpanel-diagnostics-agent/agent.py; "
        f"echo {unit_encoded} | base64 -d > /etc/systemd/system/twinpanel-diagnostics-agent.service; "
        "systemctl daemon-reload; "
        "systemctl enable --now twinpanel-diagnostics-agent.service >/dev/null; "
        "systemctl restart twinpanel-diagnostics-agent.service; "
        "sleep 1; "
        "systemctl is-active twinpanel-diagnostics-agent.service"
    )

    result = await conn.run(command, check=False, timeout=45)
    state = (result.stdout or "").strip().splitlines()[-1:] or [""]
    active = state[0].strip() == "active"
    return {
        "ok": active,
        "node_id": int(node_id),
        "service": "active" if active else state[0].strip() or "unknown",
        "stderr": (result.stderr or "")[-1200:] if not active else None,
        "agent_version": AGENT_VERSION,
    }
