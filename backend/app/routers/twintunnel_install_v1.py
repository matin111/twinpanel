"""TwinTunnel two-endpoint staging from the admin tunnel control center.

This installs and validates a versioned, disabled-by-default engine on the
Iran, exit and optional backup nodes. It deliberately does not change any
active TP27 tunnel, firewall, route, protocol, port or customer config.

True data-plane cutover requires a separately validated production carrier.
"""
from __future__ import annotations

import asyncio
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import time
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..deps import require_admin
from ..models import Node, NodeStatus, NodeType, Tunnel
from ..services.twintunnel_carrier_plan_v1 import planned_status
from .provision import ssh_connect_saved

router = APIRouter(
    prefix="/v1/tunnels",
    tags=["twintunnel-install-v1"],
    dependencies=[Depends(require_admin)],
)
ROOT = Path("/var/lib/twinpanel-license/twintunnel-install-plans")
BACKEND = Path(__file__).resolve().parents[2]
STAGER = BACKEND / "scripts/twintunnel_stage_active_nodes_v1.py"
SOURCE = BACKEND.parent / "ops/twintunnel-lab"
STAGING_BASE = "/opt/twintunnel-staging"
REVISION_RE = re.compile(r"^[a-f0-9]{20}$")
CHECK_TIMEOUT = 18


class TwinTunnelInstallIn(BaseModel):
    backup_node_id: int | None = Field(default=None, gt=0)
    mode: Literal["install", "verify"] = "install"


def _stager():
    spec = importlib.util.spec_from_file_location(
        "twintunnel_node_stager_for_admin", STAGER
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("TwinTunnel installer not included in this GitHub release")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pair(db: Session, tunnel_id: int, backup_node_id: int | None):
    tunnel = db.get(Tunnel, tunnel_id)
    if tunnel is None:
        raise HTTPException(404, detail="Tunnel not found")
    iran = db.get(Node, tunnel.iran_node_id)
    exit_node = db.get(Node, tunnel.exit_node_id)
    backup = db.get(Node, backup_node_id) if backup_node_id else None

    if iran is None or exit_node is None or (
        backup_node_id and backup is None
    ):
        raise HTTPException(404, detail="Tunnel endpoint or backup node not found")
    if iran.node_type != NodeType.IRAN or exit_node.node_type != NodeType.EXIT:
        raise HTTPException(409, detail="Tunnel endpoints have invalid roles")
    if backup:
        if backup.node_type != NodeType.EXIT:
            raise HTTPException(422, detail="Backup must be an exit/transit node")
        if backup.id in (iran.id, exit_node.id):
            raise HTTPException(422, detail="Backup must be an independent third node")
    nodes = [iran, exit_node] + ([backup] if backup else [])
    for node in nodes:
        if node.retired_at is not None or node.status != NodeStatus.ONLINE:
            raise HTTPException(409, detail=f"Node #{node.id} is not online")
        if getattr(node, "is_mother", False) or getattr(node, "agent_url", None) == "local://core":
            raise HTTPException(409, detail=f"Node #{node.id} cannot be a transit endpoint")
    return tunnel, nodes


def _record_path(tunnel_id: int) -> Path:
    return ROOT / f"tunnel-{tunnel_id}.json"


def _read_plan(tunnel_id: int) -> dict | None:
    file = _record_path(tunnel_id)
    if not file.is_file() or file.is_symlink():
        return None
    try:
        value = json.loads(file.read_text())
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) and value.get("tunnel_id") == tunnel_id else None


def _write_plan(tunnel_id: int, record: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(ROOT, 0o700)
    final = _record_path(tunnel_id)
    temp = ROOT / f".tunnel-{tunnel_id}.{os.getpid()}.json.tmp"
    try:
        with temp.open("x", encoding="utf-8") as fp:
            json.dump(record, fp, ensure_ascii=False, sort_keys=True)
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, final)
    finally:
        temp.unlink(missing_ok=True)


def _lock(tunnel_id: int) -> int:
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = ROOT / f".tunnel-{tunnel_id}.lock"
    fd = os.open(name, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(fd)
        raise HTTPException(409, detail="TwinTunnel installation already running") from exc
    return fd


def _close_lock(fd: int) -> None:
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


async def _engine_selfcheck(node_id: int, revision: str) -> dict:
    """Read-only remote version check after source staging.

    It executes only Python syntax and in-memory frame codec tests; it never
    binds a UDP socket, loads a kernel module or starts an active VPN service.
    """
    if not REVISION_RE.fullmatch(revision):
        raise RuntimeError("Invalid staged revision")
    folder = STAGING_BASE + "/" + revision
    script = """
import importlib.util
from pathlib import Path
root = Path(%r)
for name in ("udp_multiuser_mux.py","udp_turkey_transit_relay.py","udp_three_path_fault_probe.py"):
    target = root / name
    compile(target.read_bytes(),str(target),"exec")
spec = importlib.util.spec_from_file_location("ttl_mux",root/"udp_multiuser_mux.py")
mux = importlib.util.module_from_spec(spec);spec.loader.exec_module(mux)
codec = mux.Codec(b"TwinTunnel-STAGING-TEST-KEY-0001")
frame = codec.encode(1,3,901,7,b"stage-test")
assert codec.decode(frame) == (1,3,901,7,b"stage-test")
spec = importlib.util.spec_from_file_location("ttl_relay",root/"udp_turkey_transit_relay.py")
relay = importlib.util.module_from_spec(spec);spec.loader.exec_module(relay)
assert relay.flow_key(frame) == ("mux",901)
print("TT_ENGINE_SELFTEST_OK")
""" % folder
    command = "python3 - <<'PY_TWIN_ENGINE'\n" + script + "\nPY_TWIN_ENGINE"
    # Retry transient session-open failures only. Never retry bad credentials or
    # missing persisted access; all attempts remain read-only.
    conn = None
    for attempt in range(3):
        with SessionLocal() as db:
            node = db.get(Node, node_id)
            if node is None:
                return {"node_id": node_id, "ok": False, "error": "node_missing"}
            try:
                conn = await ssh_connect_saved(
                    node, db, close_read_transaction_before_ssh=True
                )
                break
            except Exception as exc:
                detail = str(getattr(exc, "detail", exc)).lower()
                fatal = (
                    getattr(exc, "status_code", None) == 409
                    or any(term in detail for term in (
                        "permission denied", "authentication failed",
                        "publickey", "private key", "کلید دسترسی",
                        "دسترسی امن این سرور ثبت نشده",
                    ))
                )
                if fatal or attempt == 2:
                    return {"node_id": node_id, "ok": False,
                            "error": type(exc).__name__ + ":ssh",
                            "ssh_attempts": attempt + 1}
        await asyncio.sleep(attempt + 1)
    assert conn is not None
    try:
        result = await asyncio.wait_for(
            conn.run(command, check=False, timeout=CHECK_TIMEOUT),
            timeout=CHECK_TIMEOUT + 3,
        )
        valid = result.exit_status == 0 and "TT_ENGINE_SELFTEST_OK" in result.stdout
        return {
            "node_id": node_id,
            "ok": valid,
            "selftest": "ok" if valid else "failed",
            "error": None if valid else (result.stderr or result.stdout)[-250:],
        }
    except Exception as exc:
        return {"node_id": node_id, "ok": False, "error": type(exc).__name__}
    finally:
        conn.close()
        await conn.wait_closed()


def _view(tunnel_id: int, tunnel: Tunnel, manifest: dict, plan: dict | None) -> dict:
    pair_matches = bool(
        plan and int(plan.get("iran_node_id", -1)) == int(tunnel.iran_node_id)
        and int(plan.get("exit_node_id", -1)) == int(tunnel.exit_node_id)
    )
    ready = bool(
        pair_matches and plan.get("status") == "staged"
        and plan.get("revision") == manifest["revision"]
        and len(plan.get("nodes", [])) == len(plan.get("node_ids") or [tunnel.iran_node_id, tunnel.exit_node_id, plan.get("backup_node_id")])
        and set(n.get("node_id") for n in plan.get("nodes", [])) == set(plan.get("node_ids") or [tunnel.iran_node_id, tunnel.exit_node_id, plan.get("backup_node_id")])
        and set(plan.get("node_ids") or [tunnel.iran_node_id, tunnel.exit_node_id, plan.get("backup_node_id")]) >= {int(tunnel.iran_node_id), int(tunnel.exit_node_id)}
        and all(n.get("ok") and n.get("selftest") == "ok" for n in plan["nodes"])
    )
    return {
        "tunnel_id": tunnel_id,
        "engine": "twintunnel_udp_mux",
        **planned_status(),
        "status": "staged" if ready else "not_staged",
        "revision": manifest["revision"],
        "installed_revision": plan.get("revision") if pair_matches else None,
        "needs_update": bool(pair_matches and plan.get("revision") != manifest["revision"]),
        "backup_node_id": plan.get("backup_node_id") if pair_matches else None,
        "nodes": plan.get("nodes", []) if pair_matches else [],
        "active_transport": tunnel.active_transport,
        "production_activated": False,
        "can_activate": False,
        "deployment_mode": "isolated_stage_only",
        "reason": (
            "Real OpenVPN UDP 77/80 packet test and full failover validation "
            "are not sufficient for production cutover. Existing TP27 remains in control."
        ),
        "staged_at": plan.get("staged_at") if pair_matches else None,
    }


@router.get("/{tunnel_id}/twintunnel-install")
def twintunnel_install_status(tunnel_id: int, db: Session = Depends(get_db)):
    tunnel, _ = _pair(db, tunnel_id, None)
    manifest = _stager().package_manifest(SOURCE)
    return _view(tunnel_id, tunnel, manifest, _read_plan(tunnel_id))


@router.post("/{tunnel_id}/twintunnel-install")
async def install_twintunnel_standby(
    tunnel_id: int,
    payload: TwinTunnelInstallIn,
    db: Session = Depends(get_db),
):
    tunnel, nodes = _pair(db, tunnel_id, payload.backup_node_id)
    stager = _stager()
    manifest = stager.package_manifest(SOURCE)
    node_ids = [int(n.id) for n in nodes]
    if len(node_ids) not in (2, 3) or len(set(node_ids)) != len(node_ids):
        raise HTTPException(422, detail="Select two tunnel endpoints; optional third transit must be unique")
    # Transaction above is read-only; close before the slow remote SSH stage.
    db.rollback()
    fd = _lock(tunnel_id)
    try:
        async def one(node_id: int):
            stage = await stager.stage_node(
                node_id, manifest, SOURCE,
                "apply" if payload.mode == "install" else "verify",
            )
            if not stage.get("ok"):
                return stage
            return {
                **stage,
                **(await _engine_selfcheck(node_id, manifest["revision"])),
            }
        # The saved-SSH connector can reject simultaneous sessions to an
        # Iran endpoint while accepting an individual connection. Serialize
        # verification to avoid false 502s and unnecessary repeat uploads.
        results = []
        for node_id in node_ids:
            result = await one(node_id)
            results.append(result)
        if not all(result.get("ok") for result in results):
            # No config or route can change on partial failure. Never mark
            # the pair as staged until every selected node passes.
            raise HTTPException(
                502,
                detail={
                    "message": "TwinTunnel staging failed; existing tunnel is untouched",
                    "nodes": results,
                },
            )
        with SessionLocal() as fresh:
            live = fresh.get(Tunnel, tunnel_id)
            if (live is None or int(live.iran_node_id) != node_ids[0]
                    or int(live.exit_node_id) != node_ids[1]):
                raise HTTPException(409, detail="Tunnel pair changed during staging")
            record = {
                "schema": 1,
                "tunnel_id": tunnel_id,
                "iran_node_id": node_ids[0],
                "exit_node_id": node_ids[1],
                "backup_node_id": node_ids[2] if len(node_ids) == 3 else None,
                "node_ids": node_ids,
                "revision": manifest["revision"],
                "status": "staged",
                "staged_at": datetime.now(timezone.utc).isoformat(),
                "nodes": results,
                "production_activated": False,
            }
            _write_plan(tunnel_id, record)
            return _view(tunnel_id, live, manifest, record)
    finally:
        _close_lock(fd)
