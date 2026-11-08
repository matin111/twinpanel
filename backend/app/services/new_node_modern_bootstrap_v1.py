from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ..models import Node, NodeProtocolConfig, NodeType
from ..protocol_account_registry import MODERN_PROTOCOL_KEYS
from ..protocol_catalog import PROTOCOL_CATALOG


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def build_modern_bootstrap_plan(db: Session, node_id: int) -> dict[str, Any]:
    target = db.query(Node).filter(Node.id == int(node_id), Node.retired_at.is_(None)).first()
    if target is None:
        raise ValueError("target node not found")
    if target.node_type != NodeType.EXIT:
        return {"node_id": int(target.id), "protocols": [], "ports": {}, "profiles": {}, "sources": {}, "already_online": [], "skipped_no_template": [], "skipped_port_conflict": [], "reason": "not_exit"}

    target_rows = {str(row.protocol): row for row in db.query(NodeProtocolConfig).filter(NodeProtocolConfig.node_id == int(target.id)).all()}
    already_online = {key for key, row in target_rows.items() if key in MODERN_PROTOCOL_KEYS and _status_value(row.status) == "online"}
    # A failed initial installation leaves an error row for its OWN port.
    # That reservation must not block a safe retry for the same protocol,
    # but every other protocol's port (including failed rows) remains
    # reserved to avoid accidental listener hijacking.
    occupied_ports: dict[int, set[str]] = {}
    for protocol, row in target_rows.items():
        if row.port is not None:
            occupied_ports.setdefault(int(row.port), set()).add(protocol)
    selected_ports: set[int] = set()

    protocols: list[str] = []
    ports: dict[str, int] = {}
    profiles: dict[str, dict[str, Any]] = {}
    sources: dict[str, dict[str, Any]] = {}
    skipped_no_template: list[str] = []
    skipped_port_conflict: list[dict[str, Any]] = []

    # Central-first bootstrap owns its runtime; it MUST NOT borrow port
    # assignments, secrets, cert paths or presets from another customer's
    # legacy Exit. All modern protocols are provisioned from the canonical
    # catalog with node-local recommended defaults in one install operation.
    for key in sorted(MODERN_PROTOCOL_KEYS):
        if key in already_online:
            continue
        definition = PROTOCOL_CATALOG.get(key) or {}
        if definition.get("runtime_status") != "ready":
            continue
        own_row = target_rows.get(key)
        chosen_port = (
            int(own_row.port) if own_row and own_row.port is not None
            else int(definition["default_port"])
        )
        blockers = occupied_ports.get(chosen_port, set()) - {key}
        if blockers or chosen_port in selected_ports:
            skipped_port_conflict.append({
                "protocol": key, "default_port": chosen_port,
                "reason": "reserved_by_other_protocol",
            })
            continue
        protocols.append(key)
        ports[key] = chosen_port
        profiles[key] = {"preset": "recommended", "settings": {}}
        sources[key] = {
            "mode": "central_catalog",
            "chosen_port": chosen_port,
            "preset": "recommended",
        }
        selected_ports.add(chosen_port)

    return {"node_id": int(target.id), "protocols": protocols, "ports": ports, "profiles": profiles, "sources": sources, "already_online": sorted(already_online), "skipped_no_template": skipped_no_template, "skipped_port_conflict": skipped_port_conflict}


async def bootstrap_new_exit_modern_protocols(db: Session, node_id: int) -> dict[str, Any]:
    """Install fresh Exit runtimes by independent daemon family.

    One failed standalone adapter (Sudoku, Mieru, etc.) must NEVER cause
    a healthy sing-box family or another standalone adapter to be
    collectively marked failed. Each group is applied using the normal
    vetted admin installer and its persisted per-protocol health checks.
    """
    plan = build_modern_bootstrap_plan(db, int(node_id))
    protocols = list(plan.get("protocols") or [])
    if not protocols:
        blocked = bool(plan.get("skipped_port_conflict") or
                       plan.get("skipped_no_template"))
        return {**plan, "ok": not blocked, "attempted": 0,
                "installed": [], "failed": [], "errors": {}}

    from fastapi import HTTPException
    from ..modern_protocol_runtime_v2 import SINGBOX_PROTOCOLS
    from ..routers.modern_protocol_admin_v3 import (
        ModernInstallV3In, ProtocolProfileIn, install,
    )

    singbox = [key for key in protocols if key in SINGBOX_PROTOCOLS]
    standalone = [key for key in protocols if key not in SINGBOX_PROTOCOLS]
    groups = ([singbox] if singbox else []) + [[key] for key in standalone]
    installed: list[str] = []
    failed: list[str] = []
    errors: dict[str, str] = {}
    for group in groups:
        payload = ModernInstallV3In(
            protocols=group,
            ports={key: int(plan["ports"][key]) for key in group},
            profiles={
                key: ProtocolProfileIn(
                    preset=str(plan["profiles"][key].get("preset") or
                               "recommended"),
                    settings=dict(plan["profiles"][key].get("settings") or {}),
                )
                for key in group
            },
        )
        try:
            result = await install(node_id=int(node_id), payload=payload, db=db)
            reported = result.get("protocols") or {}
            group_failed = set(result.get("failed_protocols") or [])
            group_failed.update(
                key for key in group
                if not isinstance(reported.get(key),dict)
                or reported[key].get("ok") is not True
            )
            for key in group:
                if key in group_failed:
                    failed.append(key)
                    errors[key] = "listener_not_healthy"
                else:
                    installed.append(key)
        except HTTPException as exc:
            db.rollback()
            failed.extend(group)
            for key in group:
                errors[key] = f"install_http_{int(exc.status_code)}"
        except Exception as exc:
            db.rollback()
            failed.extend(group)
            for key in group:
                errors[key] = f"install_error_{type(exc).__name__}"
        # Only non-sensitive telemetry: names and opaque error classes;
        # never print a remote command, private key, password or config.
        print("CENTRAL_EXIT_MODERN_INSTALL_GROUP",json.dumps({
            "node_id":int(node_id), "protocols":group,
            "installed":[key for key in group if key in installed],
            "failed":[key for key in group if key in failed],
            "errors":{key:errors[key] for key in group if key in errors},
        },sort_keys=True),flush=True)

    blocked = bool(plan.get("skipped_port_conflict") or
                   plan.get("skipped_no_template"))
    return {**plan, "ok":not failed and not blocked,
            "attempted":len(protocols), "installed":installed,
            "failed":failed, "errors":errors}
