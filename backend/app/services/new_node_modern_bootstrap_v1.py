from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ..models import Node, NodeProtocolConfig, NodeType
from ..modern_protocol_models import ModernProtocolSetting
from ..protocol_account_registry import MODERN_PROTOCOL_KEYS
from ..protocol_catalog import PROTOCOL_CATALOG
# Standalone runtime explicitly activates the four independent adapters.
# Avoid import-order dependence on the API router or a worker's imports.
from .. import standalone_protocol_runtime as _standalone_runtime  # noqa: F401


def _status_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _settings_dict(row: ModernProtocolSetting | None) -> dict[str, Any]:
    if row is None:
        return {}
    try:
        value = json.loads(row.settings_json or "{}")
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


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

    for key in MODERN_PROTOCOL_KEYS:
        if key in already_online:
            continue
        definition = PROTOCOL_CATALOG.get(key) or {}
        if definition.get("runtime_status") != "ready":
            continue
        source = (
            db.query(NodeProtocolConfig)
            .join(Node, Node.id == NodeProtocolConfig.node_id)
            .filter(Node.retired_at.is_(None), Node.node_type == NodeType.EXIT, Node.id != int(target.id), NodeProtocolConfig.protocol == key, NodeProtocolConfig.status == "online", NodeProtocolConfig.port.isnot(None))
            .order_by(NodeProtocolConfig.checked_at.desc().nullslast(), Node.id.desc())
            .first()
        )
        # A new cluster/first Exit may have no healthy template node.
        # Each adapter already ships a validated recommended catalog preset;
        # do not silently omit a purchased protocol just for lack of a source.
        # Never copy credentials or TLS certificates from another node.
        default_port = int(definition["default_port"])
        preferred_port = int(source.port) if source is not None else default_port
        chosen_port = next(
            (candidate for candidate in (preferred_port, default_port)
             if candidate not in occupied_ports),
            None,
        )
        if chosen_port is None:
            skipped_port_conflict.append({
                "protocol": key, "preferred_port": preferred_port,
                "default_port": default_port,
            })
            continue
        setting = (
            db.query(ModernProtocolSetting).filter(
                ModernProtocolSetting.node_id == int(source.node_id),
                ModernProtocolSetting.protocol == key,
            ).first()
            if source is not None else None
        )
        preset = str(setting.preset_name or "recommended") if setting else "recommended"
        saved_settings = _settings_dict(setting)
        protocols.append(key)
        ports[key] = chosen_port
        profiles[key] = {"preset": preset, "settings": saved_settings}
        sources[key] = {
            "node_id": int(source.node_id) if source is not None else None,
            "mode": "existing_node_preset" if source is not None else "catalog_default",
            "port": preferred_port,
            "chosen_port": chosen_port,
            "preset": preset,
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
