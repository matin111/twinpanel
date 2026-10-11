from __future__ import annotations

import asyncio
import fcntl
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..deps import require_admin
from ..managed_ops import (
    diagnose_managed_tunnel,
    install_ssh_relay_transport_managed,
    install_ssh_transport_managed,
    repair_managed_tunnel,
)
from ..models import Tunnel, TunnelPeerState, TunnelStatus, TunnelTransport
from ..schemas import TunnelCreate, TunnelOut
from ..tp2027_provision import (
    TP2027_PRIORITY,
    install_tp2027_overlays,
)
from . import tunnels as core

router = APIRouter(prefix="/v1/tunnels", tags=["tunnels-managed"])


# Direct/base transports. SSH Relay is intentionally on-demand: it is only
# provisioned when every direct base path is unavailable.
_TRANSPORTS = (
    ("mtunnel", 90, core.install_mtunnel_transport),
    ("backhaul", 100, core.install_backhaul_transport),
    ("ssh_tun", 200, install_ssh_transport_managed),
)


_TRANSPORT_TIMEOUTS = {
    "mtunnel": 150,
    "ssh_tun": 180,
    "backhaul": 75,
    "ssh_relay": 210,
}


_SELECTION_ORDER = (
    "quic_2027",
    "arq_2027",
    "kcp_2027",
    "tcp_2027",
    "mtunnel",
    "backhaul",
    "ssh_tun",
    "ssh_relay",
)


# Provisioning mutates systemd, interfaces, firewall state and managed
# preflight artifacts on the Iran node. A single Iran node may fan out to many
# Exit nodes, so two create/repair flows must never mutate that shared node at
# the same time. flock makes this guard effective across Uvicorn workers, not
# only inside one Python process. Different Iran nodes still provision in
# parallel because each node owns a different lock file.
@asynccontextmanager
async def _iran_provision_lock(iran_node_id: int):
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


def _detail_text(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        detail = exc.detail
        if isinstance(detail, str):
            return detail
        return str(detail)
    return str(exc)


def _mark_transport_failed(
    db: Session,
    tunnel_id: int,
    name: str,
    message: str,
) -> None:
    db.rollback()
    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == tunnel_id,
            TunnelTransport.transport == name,
        )
        .first()
    )
    if row is None:
        return

    row.status = "failed"
    row.last_error = message[:1800]
    row.updated_at = datetime.utcnow()
    db.commit()


async def _install_with_retry(
    name: str,
    installer,
    tunnel_id: int,
    db: Session,
):
    last_error: Exception | None = None
    timeout_seconds = int(_TRANSPORT_TIMEOUTS.get(name, 120))

    for attempt in (1, 2):
        try:
            return await asyncio.wait_for(
                installer(tunnel_id, db),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            db.rollback()
            raise RuntimeError(
                f"{name} install timed out after {timeout_seconds}s"
            ) from exc
        except Exception as exc:
            db.rollback()
            last_error = exc
            if attempt == 1:
                await asyncio.sleep(2)

    assert last_error is not None
    raise last_error


async def _run_transport_job(
    name: str,
    installer,
    tunnel_id: int,
) -> tuple[str, object | None, str | None, bool]:
    """Run one direct base transport in an isolated SQLAlchemy session."""

    db = SessionLocal()
    try:
        try:
            result = await _install_with_retry(
                name,
                installer,
                tunnel_id,
                db,
            )

            db.expire_all()
            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == tunnel_id,
                    TunnelTransport.transport == name,
                )
                .first()
            )

            online = bool(
                row
                and bool(row.enabled)
                and str(row.status or "").strip().lower() == "online"
            )

            if online:
                return name, result, None, True

            message = "installer returned without an online transport"
            _mark_transport_failed(db, tunnel_id, name, message)
            return name, result, message, False

        except Exception as exc:
            message = _detail_text(exc)[:1800]
            _mark_transport_failed(db, tunnel_id, name, message)
            return name, None, message, False
    finally:
        db.close()


async def _run_direct_transport_phase(
    tunnel_id: int,
) -> list[tuple[str, object | None, str | None, bool]]:
    """Install base transports deterministically, one at a time.

    All three installers touch the same Iran/Exit hosts and each may run
    managed preflight, systemd reloads, interface cleanup and firewall work.
    Running them concurrently creates a remote mutation race which becomes
    especially visible when one Iran node owns several Exit tunnels.
    """

    settled: list[tuple[str, object | None, str | None, bool]] = []

    for name, _, installer in _TRANSPORTS:
        settled.append(
            await _run_transport_job(
                name,
                installer,
                tunnel_id,
            )
        )

    return settled


async def _run_relay_job(
    tunnel_id: int,
) -> tuple[str, object | None, str | None, bool]:
    """Provision the independent SSH Relay fallback in an isolated session."""

    db = SessionLocal()
    try:
        try:
            result = await asyncio.wait_for(
                install_ssh_relay_transport_managed(tunnel_id, db),
                timeout=int(_TRANSPORT_TIMEOUTS["ssh_relay"]),
            )
            db.expire_all()
            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == tunnel_id,
                    TunnelTransport.transport == "ssh_relay",
                )
                .first()
            )
            online = bool(
                row
                and bool(row.enabled)
                and str(row.status or "").strip().lower() == "online"
            )
            if online:
                return "ssh_relay", result, None, True

            return (
                "ssh_relay",
                result,
                "relay installer returned without an online transport",
                False,
            )

        except Exception as exc:
            return "ssh_relay", None, _detail_text(exc)[:1800], False
    finally:
        db.close()


def _transport_snapshot(db: Session, tunnel_id: int) -> list[dict]:
    rows = (
        db.query(TunnelTransport)
        .filter(TunnelTransport.tunnel_id == tunnel_id)
        .order_by(TunnelTransport.priority.asc(), TunnelTransport.id.asc())
        .all()
    )

    return [
        {
            "transport": row.transport,
            "priority": row.priority,
            "enabled": bool(row.enabled),
            "status": row.status,
            "latency_ms": row.latency_ms,
            "last_error": row.last_error,
        }
        for row in rows
    ]


def _activate_best_transport(
    db: Session,
    tunnel_id: int,
) -> str | None:
    """Creation-time bootstrap only; V7 owns runtime failover afterwards."""

    tunnel = db.get(Tunnel, tunnel_id)
    if not tunnel:
        return None

    rows = {
        str(row.transport).strip().lower(): row
        for row in (
            db.query(TunnelTransport)
            .filter(TunnelTransport.tunnel_id == tunnel_id)
            .all()
        )
    }

    selected = None
    for name in _SELECTION_ORDER:
        row = rows.get(name)
        if (
            row
            and bool(row.enabled)
            and str(row.status or "").strip().lower() == "online"
        ):
            selected = row
            break

    if selected is None:
        tunnel.is_active = False
        tunnel.active_transport = None
        tunnel.status = TunnelStatus.OFFLINE
        tunnel.latency_ms = None
        db.commit()
        return None

    now = datetime.utcnow()
    selected_name = str(selected.transport)

    tunnel.mode = "auto"
    tunnel.is_active = True
    tunnel.active_transport = selected_name
    tunnel.preferred_transport = selected_name
    tunnel.status = TunnelStatus.ONLINE
    tunnel.latency_ms = selected.latency_ms
    tunnel.last_switch_at = now
    db.commit()

    return selected_name


async def _remove_failed_new_tunnel(db: Session, tunnel_id: int) -> None:
    try:
        await asyncio.wait_for(
            core.delete_tunnel(tunnel_id, db),
            timeout=45,
        )
    except BaseException:
        db.rollback()

    if db.get(Tunnel, tunnel_id) is None:
        return

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


async def _install_tp2027_phase(
    db: Session,
    tunnel_id: int,
    base_online: set[str],
) -> tuple[list[str], dict[str, str], dict[str, object]]:
    installed: list[str] = []
    errors: dict[str, str] = {}
    results: dict[str, object] = {}

    if "backhaul" not in base_online:
        errors["tp2027"] = (
            "TP2027 overlays require an online Backhaul carrier"
        )
        return installed, errors, results

    try:
        overlay = await asyncio.wait_for(
            install_tp2027_overlays(tunnel_id, db),
            timeout=210,
        )
    except Exception as exc:
        message = _detail_text(exc)[:1800]
        for name in TP2027_PRIORITY:
            errors[name] = message
        return installed, errors, results

    results["tp2027"] = overlay

    for name, item in overlay.get("transports", {}).items():
        if bool(item.get("ok")):
            installed.append(name)
        else:
            errors[name] = str(
                item.get("error")
                or "TP2027 overlay install failed"
            )[:1800]

    return installed, errors, results


async def _create_managed_tunnel_locked(
    payload: TunnelCreate,
    db: Session,
):
    existing = (
        db.query(Tunnel)
        .filter(
            Tunnel.iran_node_id == payload.iran_node_id,
            Tunnel.exit_node_id == payload.exit_node_id,
        )
        .first()
    )
    was_existing = existing is not None

    tunnel = core.register_tunnel_pair(payload, db)
    tunnel_id = int(tunnel.id)

    settled = await _run_direct_transport_phase(
        tunnel_id
    )

    installed: list[str] = []
    errors: dict[str, str] = {}
    results: dict[str, object] = {}
    base_online: set[str] = set()

    for name, result, error, online in settled:
        if result is not None:
            results[name] = result
        if online:
            installed.append(name)
            base_online.add(name)
        elif error:
            errors[name] = error

    # Direct path is genuinely unavailable: automatically try the existing
    # independent SSH Relay transport instead of blindly repeating installers.
    if not base_online:
        name, result, error, online = await _run_relay_job(tunnel_id)
        if result is not None:
            results[name] = result
        if online:
            installed.append(name)
            base_online.add(name)
        elif error:
            errors[name] = error

    overlay_installed, overlay_errors, overlay_results = (
        await _install_tp2027_phase(
            db,
            tunnel_id,
            base_online,
        )
    )

    installed.extend(overlay_installed)
    errors.update(overlay_errors)
    results.update(overlay_results)

    db.expire_all()
    primary = _activate_best_transport(db, tunnel_id)

    if primary is None:
        if not was_existing:
            await _remove_failed_new_tunnel(db, tunnel_id)

        raise HTTPException(
            status_code=502,
            detail={
                "message": (
                    "هیچ مسیر سالمی برای تانل ایجاد نشد؛ "
                    "مسیر مستقیم و Relay هر دو ناموفق بودند."
                ),
                "errors": errors,
                "tunnel_id": tunnel_id,
                "rolled_back": not was_existing,
            },
        )

    db.expire_all()
    live = db.get(Tunnel, tunnel_id)
    assert live is not None

    direct_expected = {name for name, _, _ in _TRANSPORTS}
    tp_expected = set(TP2027_PRIORITY)
    direct_complete = direct_expected <= set(installed)
    tp2027_complete = tp_expected <= set(installed)

    return {
        "ok": True,
        "operational": True,
        "complete": direct_complete,
        "tp2027_complete": tp2027_complete,
        "full_complete": direct_complete and tp2027_complete,
        "fallback_active": primary == "ssh_relay",
        "tunnel": TunnelOut.model_validate(live).model_dump(mode="json"),
        "active_transport": primary,
        "installed": installed,
        "errors": errors,
        "transports": _transport_snapshot(db, tunnel_id),
        "results": results,
        "diagnosis": diagnose_managed_tunnel(tunnel_id, db),
    }


@router.post(
    "/create-managed",
    dependencies=[Depends(require_admin)],
)
async def create_managed_tunnel(
    payload: TunnelCreate,
    db: Session = Depends(get_db),
):
    """One-click managed tunnel creation with shared-Iran serialization.

    A logical Iran node may fan out to several Exit nodes. Provisioning for the
    same Iran node is serialized across API workers, and each direct transport
    is installed deterministically instead of concurrently mutating remote
    systemd/interface/firewall state. SSH Relay remains an on-demand fallback;
    TP2027 is installed only after Backhaul is physically online. Manager V7
    owns runtime failover after provisioning.
    """

    async with _iran_provision_lock(
        int(payload.iran_node_id)
    ):
        return await _create_managed_tunnel_locked(
            payload,
            db,
        )


@router.get(
    "/{tunnel_id}/managed-diagnose",
    dependencies=[Depends(require_admin)],
)
def managed_diagnose(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    """Return dependency-aware diagnosis for managed transports and fallback."""
    try:
        return diagnose_managed_tunnel(tunnel_id, db)
    except RuntimeError as exc:
        if str(exc) == "tunnel_not_found":
            raise HTTPException(status_code=404, detail="Tunnel not found") from exc
        raise


@router.post(
    "/{tunnel_id}/managed-repair",
    dependencies=[Depends(require_admin)],
)
async def managed_repair(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    """Auto-repair direct paths, then provision SSH Relay when needed."""
    try:
        return await repair_managed_tunnel(tunnel_id, db)
    except RuntimeError as exc:
        if str(exc) == "tunnel_not_found":
            raise HTTPException(status_code=404, detail="Tunnel not found") from exc
        raise HTTPException(status_code=502, detail=str(exc)) from exc
