from __future__ import annotations

import asyncio
import fcntl
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Node, Tunnel, TunnelTransport
from .tp2027_provision import TP2027_PRIORITY, install_tp2027_overlays


EXPECTED_ORDER = (
    "quic_2027",
    "arq_2027",
    "kcp_2027",
    "tcp_2027",
    "mtunnel",
    "backhaul",
    "ssh_tun",
    "ssh_relay",
)

DIRECT_BASE_ORDER = (
    "mtunnel",
    "backhaul",
    "ssh_tun",
)

BASE_TIMEOUTS = {
    "mtunnel": 170,
    "backhaul": 90,
    "ssh_tun": 180,
    "ssh_relay": 210,
}

RELAY_PRIORITY = 300


@asynccontextmanager
async def _iran_provision_lock(iran_node_id: int):
    """Share the same cross-worker lock used by create-managed."""

    lock_path = Path(
        f"/tmp/twinpanel-managed-provision-iran-{int(iran_node_id)}.lock"
    )
    handle = lock_path.open("a+")

    try:
        await asyncio.to_thread(
            fcntl.flock,
            handle.fileno(),
            fcntl.LOCK_EX,
        )
        yield
    finally:
        try:
            await asyncio.to_thread(
                fcntl.flock,
                handle.fileno(),
                fcntl.LOCK_UN,
            )
        finally:
            handle.close()


def _status(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def _rows(db: Session, tunnel_id: int) -> dict[str, TunnelTransport]:
    return {
        str(row.transport).strip().lower(): row
        for row in (
            db.query(TunnelTransport)
            .filter(TunnelTransport.tunnel_id == int(tunnel_id))
            .all()
        )
    }


def _row_online(row: TunnelTransport | None) -> bool:
    return bool(
        row
        and bool(row.enabled)
        and _status(row.status) == "online"
    )


def diagnose_managed_tunnel(tunnel_id: int, db: Session) -> dict:
    """Dependency-aware, read-only diagnosis for managed transports.

    Runtime state is never fabricated here. Transport Manager V7 remains the
    sole runtime health/failover authority.

    ``operational`` means at least one selectable data-plane transport is
    online. ``complete`` means every normally expected direct transport is
    healthy as well. SSH Relay is an on-demand fallback and is not considered
    missing while a direct base transport is healthy.
    """

    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")

    rows = _rows(db, tunnel_id)
    backhaul_online = _row_online(rows.get("backhaul"))
    direct_online = any(
        _row_online(rows.get(name))
        for name in DIRECT_BASE_ORDER
    )
    relay_online = _row_online(rows.get("ssh_relay"))

    selectable_online = [
        name
        for name, row in rows.items()
        if name in EXPECTED_ORDER and _row_online(row)
    ]
    operational = bool(selectable_online)
    relay_required = not direct_online

    repair_needed: list[str] = []
    transports: list[dict] = []

    for name in EXPECTED_ORDER:
        row = rows.get(name)
        enabled = bool(row.enabled) if row else False
        status = _status(row.status) if row else "missing"
        issue_code: str | None = None

        if name in TP2027_PRIORITY and not backhaul_online:
            issue_code = "carrier_down"

        elif name == "ssh_relay":
            if relay_online:
                issue_code = None
            elif relay_required:
                if row is None:
                    issue_code = "relay_required"
                elif not enabled:
                    issue_code = "relay_required"
                elif status != "online":
                    issue_code = "relay_required"
            else:
                issue_code = "standby"

        elif row is None:
            issue_code = "not_installed"
        elif not enabled:
            issue_code = "disabled"
        elif status != "online":
            issue_code = "unhealthy"

        if issue_code and issue_code != "standby":
            repair_needed.append(name)

        transports.append(
            {
                "transport": name,
                "priority": getattr(row, "priority", None)
                if row is not None
                else (RELAY_PRIORITY if name == "ssh_relay" else None),
                "enabled": enabled,
                "status": "standby"
                if name == "ssh_relay" and issue_code == "standby"
                else status,
                "latency_ms": getattr(row, "latency_ms", None),
                "last_error": getattr(row, "last_error", None),
                "issue_code": issue_code,
                "dependency": "backhaul" if name in TP2027_PRIORITY else None,
            }
        )

    return {
        "ok": True,
        "tunnel_id": int(tunnel.id),
        "mode": str(getattr(tunnel, "mode", "auto") or "auto"),
        "status": _status(getattr(tunnel, "status", "offline")),
        "active_transport": getattr(tunnel, "active_transport", None),
        "preferred_transport": getattr(tunnel, "preferred_transport", None),
        "backhaul_online": backhaul_online,
        "direct_online": direct_online,
        "relay_online": relay_online,
        "relay_required": relay_required,
        "selectable_online": selectable_online,
        "repair_needed": repair_needed,
        "operational": operational,
        "healthy": operational,
        "complete": not repair_needed,
        "transports": transports,
    }


async def install_ssh_transport_managed(tunnel_id: int, db: Session):
    """Official direct SSH installer used by managed create/repair."""

    from .routers import tunnels as core

    last_error: Exception | None = None

    for attempt in (1, 2):
        try:
            return await core.install_ssh_transport(int(tunnel_id), db)
        except Exception as exc:
            db.rollback()
            last_error = exc
            if attempt == 1:
                await asyncio.sleep(2)

    assert last_error is not None
    raise last_error


async def install_ssh_relay_transport_managed(
    tunnel_id: int,
    db: Session,
):
    """Provision the existing production SSH Relay as last-resort fallback.

    Relay selection is automatic and constrained to an online, non-retired Exit
    node with saved root access. The target Exit itself and duplicate target IPs
    are excluded by ``choose_relay_node``.
    """

    from .ssh_relay import choose_relay_node, provision_ssh_relay

    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")

    iran = db.get(Node, int(tunnel.iran_node_id))
    exit_node = db.get(Node, int(tunnel.exit_node_id))
    if iran is None or exit_node is None:
        raise RuntimeError("relay_endpoint_node_missing")

    relay = choose_relay_node(db, tunnel)
    if relay is None:
        raise RuntimeError("ssh_relay_unavailable: no eligible online relay node")

    result = await provision_ssh_relay(
        tunnel,
        iran,
        relay,
        exit_node,
        db,
    )

    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == "ssh_relay",
        )
        .first()
    )
    if row is not None:
        row.priority = RELAY_PRIORITY
        db.commit()

    return {
        "relay_node_id": int(relay.id),
        "relay_public_ip": str(relay.public_ip or ""),
        "runtime": result,
    }


async def _repair_base_job(
    name: str,
    tunnel_id: int,
) -> tuple[str, bool, str | None, object | None]:
    from .routers import tunnels as core

    installers = {
        "mtunnel": core.install_mtunnel_transport,
        "backhaul": core.install_backhaul_transport,
        "ssh_tun": install_ssh_transport_managed,
    }

    db = SessionLocal()
    try:
        try:
            result = await asyncio.wait_for(
                installers[name](int(tunnel_id), db),
                timeout=int(BASE_TIMEOUTS[name]),
            )

            db.expire_all()
            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == int(tunnel_id),
                    TunnelTransport.transport == name,
                )
                .first()
            )
            online = _row_online(row)

            return (
                name,
                online,
                None if online else "installer_finished_but_transport_not_online",
                result,
            )

        except Exception as exc:
            db.rollback()
            return name, False, str(exc)[:1800], None
    finally:
        db.close()


async def _repair_relay_job(
    tunnel_id: int,
) -> tuple[str, bool, str | None, object | None]:
    db = SessionLocal()
    try:
        try:
            result = await asyncio.wait_for(
                install_ssh_relay_transport_managed(int(tunnel_id), db),
                timeout=int(BASE_TIMEOUTS["ssh_relay"]),
            )
            db.expire_all()
            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == int(tunnel_id),
                    TunnelTransport.transport == "ssh_relay",
                )
                .first()
            )
            online = _row_online(row)
            return (
                "ssh_relay",
                online,
                None if online else "relay_installer_finished_but_transport_not_online",
                result,
            )
        except Exception as exc:
            db.rollback()
            return "ssh_relay", False, str(exc)[:1800], None
    finally:
        db.close()


def _merge_unresolved_errors(after: dict, errors: dict[str, str]) -> dict[str, str]:
    merged = dict(errors)

    for item in after.get("transports", []):
        name = str(item.get("transport") or "").strip().lower()
        issue_code = str(item.get("issue_code") or "").strip().lower()

        if not name or not issue_code or issue_code == "standby":
            continue
        if name in merged:
            continue

        last_error = str(item.get("last_error") or "").strip()
        merged[name] = (last_error or issue_code)[:1800]

    return merged


async def _repair_managed_tunnel_locked(tunnel_id: int, db: Session) -> dict:
    """Diagnose and repair managed runtime, including relay fallback.

    Direct base transports are repaired first. If none becomes online, the
    existing SSH Relay transport is provisioned automatically through another
    healthy Exit node. TP2027 overlays are rebuilt only when Backhaul is online.
    Manager V7 remains authoritative for runtime selection and health.

    V15: base installers run deterministically, one at a time. They mutate the
    same remote systemd/interface/firewall state and must never overlap.
    """

    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")

    tunnel.mode = "auto"
    tunnel.is_active = True
    db.commit()

    before = diagnose_managed_tunnel(int(tunnel_id), db)
    need = set(before["repair_needed"])

    base_targets = [name for name in DIRECT_BASE_ORDER if name in need]
    base_results: dict[str, object] = {}
    errors: dict[str, str] = {}

    # TWINPANEL_MANAGED_REPAIR_SERIAL_V15
    # Never run remote-mutating installers concurrently on the same pair.
    for target in base_targets:
        name, online, error, result = await _repair_base_job(
            target,
            int(tunnel_id),
        )

        if result is not None:
            base_results[name] = result
        if not online and error:
            errors[name] = error

    db.expire_all()
    rows = _rows(db, tunnel_id)
    direct_online = any(
        _row_online(rows.get(name))
        for name in DIRECT_BASE_ORDER
    )

    relay_result = None
    if not direct_online:
        name, relay_ok, relay_error, relay_result = await _repair_relay_job(
            int(tunnel_id)
        )
        if relay_result is not None:
            base_results[name] = relay_result
        if not relay_ok and relay_error:
            errors[name] = relay_error

    db.expire_all()
    rows = _rows(db, tunnel_id)
    backhaul_online = _row_online(rows.get("backhaul"))

    overlay_result = None
    overlay_needed = any(name in need for name in TP2027_PRIORITY)

    if overlay_needed and backhaul_online:
        try:
            overlay_result = await asyncio.wait_for(
                install_tp2027_overlays(int(tunnel_id), db),
                timeout=240,
            )
        except Exception as exc:
            db.rollback()
            message = str(exc)[:1800]
            for name in TP2027_PRIORITY:
                errors[name] = message

    elif overlay_needed and not backhaul_online:
        for name in TP2027_PRIORITY:
            errors[name] = "carrier_down: backhaul is not online"

    await asyncio.sleep(12)
    db.expire_all()
    after = diagnose_managed_tunnel(int(tunnel_id), db)
    errors = _merge_unresolved_errors(after, errors)

    operational = bool(after.get("operational"))
    attempted = bool(base_targets or overlay_needed or not direct_online)
    partial = bool(operational and after.get("repair_needed"))

    return {
        "ok": operational,
        "healthy": operational,
        "operational": operational,
        "complete": bool(after.get("complete")),
        "partial": partial,
        "tunnel_id": int(tunnel_id),
        "mode": "auto",
        "provisioning_mode": "panel_serial_v15",
        "before": before,
        "after": after,
        "base_results": base_results,
        "ssh_relay_result": relay_result,
        "tp2027_result": overlay_result,
        "errors": errors,
        "remaining": list(after.get("repair_needed") or []),
        "attempted": attempted,
        "repaired_at": datetime.utcnow().isoformat() + "Z",
    }


async def repair_managed_tunnel(tunnel_id: int, db: Session) -> dict:
    """Serialize managed repair against create/repair on the same Iran node."""

    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")

    iran_node_id = int(tunnel.iran_node_id)

    async with _iran_provision_lock(iran_node_id):
        return await _repair_managed_tunnel_locked(
            int(tunnel_id),
            db,
        )
