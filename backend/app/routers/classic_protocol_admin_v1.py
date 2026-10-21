from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Node, NodeProtocolConfig
from ..node_runtime_connection import (
    connect_protocol_runtime,
    is_protocol_runtime_node,
    protocol_runtime_node_clause,
)
from ..protocol_adapter_registry import (
    CLASSIC_PROTOCOL_KEYS,
    CLASSIC_PROTOCOL_REGISTRY,
    REGISTRY_SCHEMA_VERSION,
    classic_catalog_payload,
    classic_definition,
    unified_registry_payload,
)
from .provision import (
    ProtocolSettings,
    _protocol_live_health,
    _protocol_settings_from_db,
    _restart_protocol_service,
    _save_live_health,
    cmd,
    ensure_base,
    provision_protocols,
)


router = APIRouter(
    prefix="/v1/provision",
    tags=["provision", "protocol-studio"],
    dependencies=[Depends(require_admin)],
)


ClassicProtocol = Literal[
    "cisco",
    "openvpn",
    "wireguard",
    "l2tp",
    "v2ray",
]
ClassicPreset = Literal[
    "recommended",
    "performance",
    "compatibility",
    "custom",
]

_CLASSIC_PROTOCOLS = CLASSIC_PROTOCOL_KEYS


class EnsureClassicProtocolIn(BaseModel):
    node_id: int = Field(gt=0)
    protocol: ClassicProtocol
    port: int | None = Field(default=None, ge=1, le=65535)
    transport: Literal["udp", "tcp"] | None = None
    preset: ClassicPreset = "custom"

    @model_validator(mode="after")
    def validate_protocol_options(self):
        if self.protocol == "l2tp" and self.port is not None:
            raise ValueError("L2TP/IPsec uses fixed UDP ports 500/4500/1701")
        if self.protocol != "openvpn" and self.transport is not None:
            raise ValueError("transport override is only supported for OpenVPN")
        return self


class ClassicProtocolControlIn(BaseModel):
    node_id: int = Field(gt=0)
    protocol: ClassicProtocol | None = None


def _existing_config(
    db: Session,
    node_id: int,
    protocol: str,
) -> NodeProtocolConfig | None:
    return (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == node_id,
            NodeProtocolConfig.protocol == protocol,
        )
        .first()
    )


def _preset_values(payload: EnsureClassicProtocolIn) -> dict:
    if payload.preset == "custom":
        return {}
    definition = CLASSIC_PROTOCOL_REGISTRY[payload.protocol]
    return dict(definition.get("presets", {}).get(payload.preset, {}))


def _default_port(protocol: str) -> int | None:
    value = CLASSIC_PROTOCOL_REGISTRY[protocol].get("default_port")
    return int(value) if value is not None else None


def _default_transport(protocol: str) -> str:
    return str(CLASSIC_PROTOCOL_REGISTRY[protocol].get("transport") or "")


def _default_port_text(protocol: str) -> str:
    definition = CLASSIC_PROTOCOL_REGISTRY[protocol]
    value = str(definition.get("port_text") or "").strip()
    if value:
        return value
    port = _default_port(protocol)
    return str(port) if port else ""


def _settings_for(
    payload: EnsureClassicProtocolIn,
    existing: NodeProtocolConfig | None,
) -> ProtocolSettings:
    values = {
        "install_cisco": False,
        "install_openvpn": False,
        "install_wireguard": False,
        "install_l2tp": False,
        "install_v2ray": False,
    }

    protocol = payload.protocol
    values[f"install_{protocol}"] = True
    preset = _preset_values(payload)

    if protocol == "cisco":
        values["cisco_port"] = int(
            payload.port
            or preset.get("port")
            or (existing.port if existing and existing.port else 0)
            or _default_port(protocol)
            or 443
        )

    elif protocol == "openvpn":
        values["openvpn_port"] = int(
            payload.port
            or preset.get("port")
            or (existing.port if existing and existing.port else 0)
            or _default_port(protocol)
            or 1194
        )
        saved_transport = str(
            existing.transport if existing else ""
        ).strip().lower()
        preset_transport = str(preset.get("transport") or "").strip().lower()
        values["openvpn_transport"] = (
            payload.transport
            or (preset_transport if preset_transport in {"udp", "tcp"} else None)
            or (saved_transport if saved_transport in {"udp", "tcp"} else "udp")
        )

    elif protocol == "wireguard":
        values["wireguard_port"] = int(
            payload.port
            or preset.get("port")
            or (existing.port if existing and existing.port else 0)
            or _default_port(protocol)
            or 51820
        )

    elif protocol == "v2ray":
        values["xray_port"] = int(
            payload.port
            or preset.get("port")
            or (existing.port if existing and existing.port else 0)
            or _default_port(protocol)
            or 8443
        )

    return ProtocolSettings(**values)


def _runtime_node(db: Session, node_id: int) -> Node:
    node = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == int(node_id),
        )
        .first()
    )
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    if not is_protocol_runtime_node(node):
        raise HTTPException(
            status_code=422,
            detail="پروتکل‌های دسترسی فقط روی نود خروجی یا TwinPanel Local Core نصب می‌شوند",
        )
    return node


@router.get("/protocol-registry")
def protocol_registry():
    """Unified, capability-aware catalog for Protocol Studio.

    The registry is descriptive and fail-closed. In particular, classic
    disable/uninstall remains false until a separately audited adapter exists.
    Runtime execution continues through the existing production adapters.
    """

    return unified_registry_payload()


@router.get("/classic-protocols")
def classic_protocol_inventory(
    db: Session = Depends(get_db),
):
    nodes = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            protocol_runtime_node_clause(),
        )
        .order_by(Node.id.asc())
        .all()
    )

    node_ids = [node.id for node in nodes]
    configs = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id.in_(node_ids),
            NodeProtocolConfig.protocol.in_(_CLASSIC_PROTOCOLS),
        )
        .all()
        if node_ids
        else []
    )
    config_map = {
        (row.node_id, row.protocol): row
        for row in configs
    }

    payload_nodes = []
    for node in nodes:
        protocols = []
        for protocol in _CLASSIC_PROTOCOLS:
            definition = classic_definition(protocol)
            row = config_map.get((node.id, protocol))
            enabled = bool(getattr(node, f"enable_{protocol}", False))
            port = (
                int(row.port)
                if row and row.port
                else _default_port(protocol)
            )
            transport = (
                str(row.transport or "").strip().lower()
                if row
                else ""
            ) or _default_transport(protocol)
            port_text = (
                str(row.port_text or "").strip()
                if row
                else ""
            ) or _default_port_text(protocol)
            protocols.append(
                {
                    "protocol": protocol,
                    "enabled": enabled,
                    "port": port,
                    "port_text": port_text,
                    "transport": transport,
                    "service": row.service_name if row else None,
                    "status": row.status if row else (
                        "enabled" if enabled else "not_installed"
                    ),
                    "last_error": row.last_error if row else None,
                    "checked_at": row.checked_at if row else None,
                    "core": definition["core"],
                    "adapter": definition["adapter"],
                    "runtime_status": definition["runtime_status"],
                    "capabilities": definition["capabilities"],
                }
            )

        payload_nodes.append(
            {
                "id": node.id,
                "name": node.name,
                "public_ip": node.public_ip,
                "public_domain": node.public_domain,
                "status": getattr(node.status, "value", node.status),
                "protocols": protocols,
            }
        )

    return {
        "ok": True,
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "catalog": classic_catalog_payload(),
        "nodes": payload_nodes,
    }


@router.post("/ensure-classic-protocol")
async def ensure_classic_protocol(
    payload: EnsureClassicProtocolIn,
    db: Session = Depends(get_db),
):
    node = _runtime_node(db, payload.node_id)
    existing = _existing_config(
        db,
        node.id,
        payload.protocol,
    )
    settings = _settings_for(payload, existing)

    conn = await connect_protocol_runtime(node, db)
    try:
        os_id = (
            await cmd(
                conn,
                ". /etc/os-release && printf '%s' \"$ID\"",
                check=False,
            )
        ).strip().lower()
        if os_id not in {"ubuntu", "debian"}:
            raise HTTPException(
                status_code=400,
                detail="نصب مدیریت‌شده پروتکل فعلاً روی Ubuntu/Debian پشتیبانی می‌شود",
            )

        await ensure_base(conn)

        results, failed, _secrets = await provision_protocols(
            conn,
            settings,
            db,
            node,
            repair=True,
        )
        result = results.get(payload.protocol, {})

        if payload.protocol in failed:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "نصب یا Repair پروتکل کامل نشد",
                    "protocol": payload.protocol,
                    "result": result,
                },
            )

        db.refresh(node)
        return {
            "ok": True,
            "node_id": node.id,
            "protocol": payload.protocol,
            "adapter": CLASSIC_PROTOCOL_REGISTRY[payload.protocol]["adapter"],
            "preset": payload.preset,
            "runtime": result,
            "enabled": bool(
                getattr(node, f"enable_{payload.protocol}", False)
            ),
            "execution": "local" if getattr(node, "is_mother", False) else "ssh",
            "message": "پروتکل نصب/Repair و Health Check شد",
        }

    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/classic-protocol-health")
async def classic_protocol_health(
    payload: ClassicProtocolControlIn,
    db: Session = Depends(get_db),
):
    node = _runtime_node(db, payload.node_id)
    conn = await connect_protocol_runtime(node, db)
    try:
        stored = _protocol_settings_from_db(db, node.id)
        names = [payload.protocol] if payload.protocol else list(_CLASSIC_PROTOCOLS)
        results = {}
        for protocol in names:
            result = await _protocol_live_health(conn, protocol, stored.get(protocol))
            result["protocol"] = protocol
            result["name"] = CLASSIC_PROTOCOL_REGISTRY[protocol]["title"]
            results[protocol] = result
            _save_live_health(db, node, protocol, result)
        db.commit()
        return {
            "ok": all(item["ok"] for item in results.values()),
            "node_id": node.id,
            "execution": "local" if getattr(node, "is_mother", False) else "ssh",
            "protocols": results,
            "message": "بررسی سرویس‌ها انجام شد",
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/classic-restart-protocol")
async def classic_restart_protocol(
    payload: ClassicProtocolControlIn,
    db: Session = Depends(get_db),
):
    node = _runtime_node(db, payload.node_id)
    if not payload.protocol:
        raise HTTPException(status_code=400, detail="پروتکل برای ریستارت مشخص نشده است")

    conn = await connect_protocol_runtime(node, db)
    try:
        stored = _protocol_settings_from_db(db, node.id)
        used_service = await _restart_protocol_service(
            conn,
            payload.protocol,
            stored.get(payload.protocol),
        )
        result = await _protocol_live_health(
            conn,
            payload.protocol,
            stored.get(payload.protocol),
        )
        result["protocol"] = payload.protocol
        result["restarted_service"] = used_service
        result["name"] = CLASSIC_PROTOCOL_REGISTRY[payload.protocol]["title"]
        _save_live_health(db, node, payload.protocol, result)
        db.commit()
        return {
            "ok": result["ok"],
            "node_id": node.id,
            "execution": "local" if getattr(node, "is_mother", False) else "ssh",
            "protocol": result,
            "message": (
                f"{CLASSIC_PROTOCOL_REGISTRY[payload.protocol]['title']} ریستارت شد و سالم است"
                if result["ok"]
                else f"{CLASSIC_PROTOCOL_REGISTRY[payload.protocol]['title']} ریستارت شد اما Health Check ناموفق بود"
            ),
        }
    finally:
        conn.close()
        await conn.wait_closed()