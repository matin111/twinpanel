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
    occupied_ports = {int(row.port) for row in target_rows.values() if row.port is not None}

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
        chosen_port = int(definition["default_port"])
        if chosen_port in occupied_ports:
            skipped_port_conflict.append({
                "protocol": key, "default_port": chosen_port,
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
        occupied_ports.add(chosen_port)

    return {"node_id": int(target.id), "protocols": protocols, "ports": ports, "profiles": profiles, "sources": sources, "already_online": sorted(already_online), "skipped_no_template": skipped_no_template, "skipped_port_conflict": skipped_port_conflict}


async def bootstrap_new_exit_modern_protocols(db: Session, node_id: int) -> dict[str, Any]:
    plan = build_modern_bootstrap_plan(db, int(node_id))
    protocols = list(plan.get("protocols") or [])
    if not protocols:
        return {**plan, "ok": True, "attempted": 0, "installed": [], "failed": []}

    from ..routers.modern_protocol_admin_v3 import ModernInstallV3In, ProtocolProfileIn, install

    payload = ModernInstallV3In(
        protocols=protocols,
        ports={key: int(value) for key, value in (plan.get("ports") or {}).items()},
        profiles={key: ProtocolProfileIn(preset=str(value.get("preset") or "recommended"), settings=dict(value.get("settings") or {})) for key, value in (plan.get("profiles") or {}).items()},
    )
    result = await install(node_id=int(node_id), payload=payload, db=db)
    failed = list(result.get("failed_protocols") or [])
    installed = [key for key in protocols if key not in set(failed)]
    return {**plan, "ok": not failed, "attempted": len(protocols), "installed": installed, "failed": failed, "installer": result}
