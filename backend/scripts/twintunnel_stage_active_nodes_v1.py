#!/usr/bin/env python3
"""Stage TwinTunnel lab source on ALL online nodes, including active TP27 endpoints.

The source of truth is the GitHub-built release's ops/twintunnel-lab directory.
This installer is deliberately NON-ACTIVATING: no restart, firewall, routing,
service, daemon enablement or VPN profile changes. It only stages verified files.
Usage (from a release with backend environment set):
  python backend/scripts/twintunnel_stage_active_nodes_v1.py --dry-run
  python backend/scripts/twintunnel_stage_active_nodes_v1.py --apply
  python backend/scripts/twintunnel_stage_active_nodes_v1.py --verify
Optional --node-id N selects one active endpoint as a first canary.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shlex
import sys
import tempfile

ARTIFACTS = (
    "udp_multiuser_mux.py",
    "udp_turkey_transit_relay.py",
    "udp_three_path_fault_probe.py",
)
STAGE_BASE = "/opt/twintunnel-staging"
MIN_ACTIVE_TUNNELS = 1


def package_manifest(source_root: Path) -> dict:
    """Release-local files only: no HTTP downloads, keys, or runtime configs."""
    checksums = {}
    for name in ARTIFACTS:
        file = source_root / name
        if not file.is_file() or file.is_symlink():
            raise RuntimeError("release_artifact_missing:" + name)
        data = file.read_bytes()
        if not 500 <= len(data) <= 200_000:
            raise RuntimeError("invalid_artifact_size:" + name)
        checksums[name] = hashlib.sha256(data).hexdigest()
    raw = json.dumps(checksums, sort_keys=True, separators=(",", ":")).encode()
    revision = hashlib.sha256(raw).hexdigest()[:20]
    return {"schema": 1, "revision": revision, "sha256": checksums, "active": False}


def active_endpoints(db):
    """Inventory comes from current active tunnels; never a stale hardcoded list."""
    from app.models import Node, NodeStatus, Tunnel
    rows = (
        db.query(Tunnel)
        .filter(Tunnel.is_active.is_(True), Tunnel.active_transport == "tp27_fast")
        .order_by(Tunnel.id.asc())
        .all()
    )
    if len(rows) < MIN_ACTIVE_TUNNELS:
        raise RuntimeError("no_active_tp27_tunnels_abort")
    active_tunnel_ids = {
        int(n) for t in rows for n in (t.iran_node_id, t.exit_node_id)
    }
    # Every online node gets a staged package (including central/standalone
    # nodes with no active tunnel yet), not just existing TP27 pair members.
    nodes = (
        db.query(Node)
        .filter(Node.retired_at.is_(None), Node.status == NodeStatus.ONLINE)
        .order_by(Node.id.asc())
        .all()
    )
    ids = {int(n.id) for n in nodes}
    if not active_tunnel_ids.issubset(ids):
        raise RuntimeError("active_tunnel_endpoint_not_online_abort")
    summary = [
        {"tunnel": int(t.id), "iran_id": int(t.iran_node_id),
         "exit_id": int(t.exit_node_id), "transport": str(t.active_transport)}
        for t in rows
    ]
    return summary, nodes


async def stage_node(node_id: int, manifest: dict, root: Path, mode: str) -> dict:
    from app.database import SessionLocal
    from app.models import Node
    from app.routers.provision import ssh_connect_saved

    with SessionLocal() as db:
        node = db.query(Node).filter(Node.id == node_id).first()
        if node is None:
            return {"node_id": node_id, "ok": False, "error": "node_missing"}
        name = str(node.name)
        # Reuse the panel's existing saved keys; no credentials in logs/artifacts.
        try:
            conn = await ssh_connect_saved(
                node, db, close_read_transaction_before_ssh=True
            )
        except Exception as exc:
            return {"node_id": node_id, "name": name, "ok": False,
                    "error": type(exc).__name__ + ":ssh_unavailable"}

    folder = STAGE_BASE + "/" + manifest["revision"]
    try:
        # No root= non-root paths; all staging is outside the active TP27 units.
        identity = await conn.run("id -u", check=False, timeout=8)
        if identity.exit_status != 0 or identity.stdout.strip() != "0":
            raise RuntimeError("remote_root_required_for_versioned_stage")
        if mode == "apply":
            made = await conn.run(
                "install -d -m 0755 " + shlex.quote(folder),
                check=False, timeout=12,
            )
            if made.exit_status != 0:
                raise RuntimeError("staging_directory_creation_failed")
            async with conn.start_sftp_client() as sftp:
                for filename in ARTIFACTS:
                    dst = folder + "/" + filename
                    tmp = dst + ".upload"
                    await sftp.put(str(root / filename), tmp)
                    move = await conn.run(
                        "chmod 0644 " + shlex.quote(tmp)
                        + " && mv -f " + shlex.quote(tmp)
                        + " " + shlex.quote(dst),
                        check=False, timeout=12,
                    )
                    if move.exit_status != 0:
                        raise RuntimeError("atomic_staging_failed:" + filename)
                with tempfile.TemporaryDirectory(prefix="ttstage-") as d:
                    mp = Path(d) / "manifest.json"
                    mp.write_text(json.dumps(manifest, sort_keys=True) + "\n")
                    tmp = folder + "/manifest.json.upload"
                    dst = folder + "/manifest.json"
                    await sftp.put(str(mp), tmp)
                    move = await conn.run(
                        "chmod 0644 " + shlex.quote(tmp)
                        + " && mv -f " + shlex.quote(tmp)
                        + " " + shlex.quote(dst),
                        check=False, timeout=12,
                    )
                    if move.exit_status != 0:
                        raise RuntimeError("manifest_stage_failed")
        # Verification is read-only, including on future versioned releases.
        for filename in ARTIFACTS:
            dst = folder + "/" + filename
            check = await conn.run(
                "sha256sum " + shlex.quote(dst),
                check=False, timeout=12,
            )
            actual = check.stdout.strip().split(" ")[0] if check.exit_status == 0 else ""
            if actual != manifest["sha256"][filename]:
                raise RuntimeError("sha256_verification_failed:" + filename)
        marker = await conn.run(
            "cat " + shlex.quote(folder + "/manifest.json"),
            check=False, timeout=12,
        )
        if marker.exit_status != 0:
            raise RuntimeError("staging_manifest_missing")
        saved = json.loads(marker.stdout)
        if saved != manifest or saved.get("active") is not False:
            raise RuntimeError("staging_manifest_mismatch")
        return {"node_id": node_id, "name": name, "ok": True,
                "revision": manifest["revision"], "mode": mode,
                "active_transport_changed": False}
    except Exception as exc:
        return {"node_id": node_id, "name": name, "ok": False,
                "error": str(exc)[:180]}
    finally:
        conn.close()
        await conn.wait_closed()


async def execute(args) -> int:
    logging.getLogger("asyncssh").setLevel(logging.WARNING)
    from app.database import SessionLocal
    root = (
        Path(args.source_root).resolve()
        if args.source_root else
        Path(__file__).resolve().parents[2] / "ops" / "twintunnel-lab"
    )
    manifest = package_manifest(root)
    with SessionLocal() as db:
        tunnels, nodes = active_endpoints(db)
        selected = [int(n.id) for n in nodes]
        if args.node_id is not None:
            if args.node_id not in selected:
                raise RuntimeError("requested_node_not_active_tp27_endpoint")
            selected = [args.node_id]
        inventory = [{"id": int(n.id), "name": str(n.name)} for n in nodes]
    print("TWINTUNNEL_ACTIVE_TUNNELS " + json.dumps(tunnels), flush=True)
    print("TWINTUNNEL_NODE_INVENTORY " + json.dumps(inventory), flush=True)
    print("TWINTUNNEL_STAGE_REVISION " + manifest["revision"], flush=True)
    if args.dry_run:
        print("TWINTUNNEL_DRY_RUN " + json.dumps(
            {"mode": "dry_run", "target_node_ids": selected,
             "ssh_changes": False, "routing_changes": False,
             "vpn_service_restarts": False, "customer_config_changes": False}
        ), flush=True)
        return 0
    sem = asyncio.Semaphore(args.concurrency)
    async def task(node_id):
        async with sem:
            result = await stage_node(
                node_id, manifest, root, "apply" if args.apply else "verify"
            )
            print("TWINTUNNEL_NODE_STAGE " + json.dumps(result), flush=True)
            return result
    results = await asyncio.gather(*(task(n) for n in selected))
    ok = sum(bool(r["ok"]) for r in results)
    print("TWINTUNNEL_STAGE_SUMMARY " + json.dumps(
        {"target": len(selected), "verified": ok,
         "failed": len(selected) - ok, "revision": manifest["revision"],
         "production_data_plane_changed": False}
    ), flush=True)
    return 0 if ok == len(selected) else 2


def parse_args():
    p = argparse.ArgumentParser()
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    p.add_argument("--node-id", type=int, default=None)
    p.add_argument("--concurrency", type=int, choices=range(1, 5), default=3)
    p.add_argument("--source-root", default=None)
    return p.parse_args()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(execute(parse_args())))
    except Exception as exc:
        print("TWINTUNNEL_STAGE_FATAL " + type(exc).__name__ + ":" +
              str(exc)[:180], flush=True)
        sys.exit(2)
