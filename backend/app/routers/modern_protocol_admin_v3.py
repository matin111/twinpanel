from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Node, NodeProtocolConfig
from ..modern_protocol_models import ModernProtocolSetting
from ..modern_node_install_lock import NodeInstallBusy, exclusive_node_install
from ..modern_protocol_runtime import certificate_pin
from ..modern_protocol_dispatch import (
    SINGBOX_PROTOCOLS,
    ModernRuntimeV2Error,
    apply_profiles,
    profile_health,
    redacted_preview,
    remove_profile,
)
from ..node_runtime_connection import (
    connect_protocol_runtime,
    is_protocol_runtime_node,
    protocol_runtime_node_clause,
)
from ..protocol_catalog import (
    PROTOCOL_CATALOG,
    SCHEMA_VERSION,
    catalog_payload,
    resolve_settings,
    settings_hash,
)


router = APIRouter(
    prefix="/v1/settings/vpn",
    tags=["modern-protocols-v3"],
    dependencies=[Depends(require_admin)],
)


class ProtocolProfileIn(BaseModel):
    preset: str = "recommended"
    settings: dict[str, Any] = Field(default_factory=dict)


class ModernInstallV3In(BaseModel):
    protocols: list[str]
    ports: dict[str, int] = Field(default_factory=dict)
    profiles: dict[str, ProtocolProfileIn] = Field(default_factory=dict)


class ModernPreviewIn(BaseModel):
    protocol: str
    port: int | None = None
    preset: str = "recommended"
    settings: dict[str, Any] = Field(default_factory=dict)


class ModernHealthV3In(BaseModel):
    protocols: list[str] | None = None


def _protocol_node(db: Session, node_id: int) -> Node:
    node = (
        db.query(Node)
        .filter(Node.id == int(node_id), Node.retired_at.is_(None))
        .first()
    )
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    if not is_protocol_runtime_node(node):
        raise HTTPException(
            status_code=400,
            detail="پروتکل‌های مدرن فقط روی نود خروجی یا TwinPanel Local Core نصب می‌شوند",
        )
    return node


def _status_rows(db: Session, node_id: int) -> dict[str, NodeProtocolConfig]:
    keys = list(PROTOCOL_CATALOG)
    rows = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == int(node_id),
            NodeProtocolConfig.protocol.in_(keys),
        )
        .all()
    )
    return {str(row.protocol): row for row in rows}


def _setting_rows(db: Session, node_id: int) -> dict[str, ModernProtocolSetting]:
    rows = (
        db.query(ModernProtocolSetting)
        .filter(ModernProtocolSetting.node_id == int(node_id))
        .all()
    )
    return {str(row.protocol): row for row in rows}


def _safe_settings(row: ModernProtocolSetting | None) -> dict[str, Any]:
    if not row:
        return {}
    try:
        value = json.loads(row.settings_json or "{}")
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _row_payload(
    key: str,
    status: NodeProtocolConfig | None,
    setting: ModernProtocolSetting | None,
) -> dict[str, Any]:
    definition = PROTOCOL_CATALOG[key]
    saved = _safe_settings(setting)
    preset = setting.preset_name if setting else "recommended"
    try:
        _, effective, warnings = resolve_settings(key, preset, saved)
    except Exception:
        preset = "custom"
        effective = saved
        warnings = ["saved_settings_need_review"]
    return {
        "protocol": key,
        "name": definition["title"],
        "category": definition["category"],
        "core": definition["core"],
        "adapter": definition["adapter"],
        "runtime_status": definition["runtime_status"],
        "installable": definition["runtime_status"] == "ready",
        "port": int(status.port) if status and status.port else int(definition["default_port"]),
        "transport": status.transport if status and status.transport else definition["transport"],
        "service": status.service_name if status and status.service_name else (
            "twinpanel-sing-box" if definition["adapter"] == "sing-box" else definition["core"]
        ),
        "status": status.status if status else "not_installed",
        "last_error": status.last_error if status else None,
        "checked_at": status.checked_at.isoformat() + "Z" if status and status.checked_at else None,
        "preset": preset,
        "settings": saved,
        "effective_settings": effective,
        "warnings": warnings,
        "config_hash": setting.config_hash if setting else None,
        "last_applied_at": (
            setting.last_applied_at.isoformat() + "Z"
            if setting and setting.last_applied_at else None
        ),
    }


def _save_status(
    db: Session,
    node: Node,
    key: str,
    result: dict[str, Any],
) -> NodeProtocolConfig:
    row = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == node.id,
            NodeProtocolConfig.protocol == key,
        )
        .first()
    )
    if not row:
        row = NodeProtocolConfig(node_id=node.id, protocol=key)
        db.add(row)
    definition = PROTOCOL_CATALOG[key]
    row.port = int(result.get("port") or definition["default_port"])
    row.port_text = str(row.port)
    row.transport = str(result.get("transport") or definition["transport"])
    row.service_name = str(result.get("service") or definition["core"])
    row.status = "online" if result.get("ok") else "error"
    row.last_error = None if result.get("ok") else str(
        result.get("error") or "service_or_listener_unhealthy"
    )[:1800]
    row.checked_at = datetime.utcnow()
    return row


def _save_setting(
    db: Session,
    node_id: int,
    key: str,
    preset: str,
    settings: dict[str, Any],
    port: int,
) -> ModernProtocolSetting:
    row = (
        db.query(ModernProtocolSetting)
        .filter(
            ModernProtocolSetting.node_id == int(node_id),
            ModernProtocolSetting.protocol == key,
        )
        .first()
    )
    if not row:
        row = ModernProtocolSetting(node_id=int(node_id), protocol=key)
        db.add(row)
    row.preset_name = preset
    row.settings_json = json.dumps(settings, ensure_ascii=False, separators=(",", ":"))
    row.schema_version = SCHEMA_VERSION
    row.config_hash = settings_hash(key, port, preset, settings)
    row.last_applied_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    return row


def _normalize_protocols(values: list[str]) -> list[str]:
    result: list[str] = []
    for raw in values or []:
        key = str(raw or "").strip().lower()
        if key not in PROTOCOL_CATALOG:
            raise HTTPException(status_code=422, detail=f"پروتکل نامعتبر: {key or raw}")
        if key not in result:
            result.append(key)
    if not result:
        raise HTTPException(status_code=422, detail="حداقل یک پروتکل انتخاب کنید")
    return result


def _port_for(key: str, supplied: dict[str, int]) -> int:
    try:
        port = int(supplied.get(key, PROTOCOL_CATALOG[key]["default_port"]))
    except Exception:
        raise HTTPException(status_code=422, detail=f"پورت {key} معتبر نیست") from None
    if not 1 <= port <= 65535:
        raise HTTPException(status_code=422, detail=f"پورت {key} خارج از بازه است")
    return port


@router.get("/modern-protocols")
def inventory(db: Session = Depends(get_db)):
    nodes = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            protocol_runtime_node_clause(),
        )
        .order_by(Node.id.asc())
        .all()
    )
    payload: list[dict[str, Any]] = []
    for node in nodes:
        statuses = _status_rows(db, node.id)
        settings = _setting_rows(db, node.id)
        payload.append({
            "id": node.id,
            "name": node.name,
            "public_ip": node.public_ip,
            "public_domain": node.public_domain,
            "status": getattr(node.status, "value", str(node.status)),
            "protocols": [
                _row_payload(key, statuses.get(key), settings.get(key))
                for key in PROTOCOL_CATALOG
            ],
        })
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "catalog": catalog_payload(),
        "nodes": payload,
    }


@router.post("/modern-protocols/{node_id}/preview")
def preview(
    node_id: int,
    payload: ModernPreviewIn,
    db: Session = Depends(get_db),
):
    _protocol_node(db, node_id)
    key = str(payload.protocol or "").strip().lower()
    if key not in PROTOCOL_CATALOG:
        raise HTTPException(status_code=422, detail="پروتکل معتبر نیست")
    port = _port_for(key, {key: payload.port} if payload.port else {})
    try:
        preset, effective, warnings = resolve_settings(
            key,
            payload.preset,
            payload.settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "ok": True,
        "protocol": key,
        "preset": preset,
        "effective_settings": effective,
        "warnings": warnings,
        "preview": redacted_preview(key, port, effective),
        "config_hash": settings_hash(key, port, preset, effective),
        "runtime_status": PROTOCOL_CATALOG[key]["runtime_status"],
    }


@router.post("/modern-protocols/{node_id}/install")
async def install(
    node_id: int,
    payload: ModernInstallV3In,
    db: Session = Depends(get_db),
):
    node = _protocol_node(db, node_id)
    protocols = _normalize_protocols(payload.protocols)

    unavailable = [
        key for key in protocols
        if PROTOCOL_CATALOG[key]["runtime_status"] != "ready"
    ]
    if unavailable:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Runtime این پروتکل هنوز آماده نصب نیست",
                "protocols": unavailable,
            },
        )

    profiles: list[dict[str, Any]] = []
    resolved_by_key: dict[str, tuple[str, dict[str, Any], list[str], int]] = {}
    used_ports: set[int] = set()
    for key in protocols:
        port = _port_for(key, payload.ports)
        if port in used_ports:
            raise HTTPException(status_code=409, detail="پروتکل‌ها نمی‌توانند پورت یکسان داشته باشند")
        used_ports.add(port)
        profile = payload.profiles.get(key) or ProtocolProfileIn()
        try:
            preset, effective, warnings = resolve_settings(key, profile.preset, profile.settings)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        resolved_by_key[key] = (preset, effective, warnings, port)
        profiles.append({"protocol": key, "port": port, "settings": effective})

    conflicts = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == node.id,
            NodeProtocolConfig.port.in_(list(used_ports)),
            ~NodeProtocolConfig.protocol.in_(protocols),
        )
        .all()
    )
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "یکی از پورت‌ها قبلاً توسط پروتکل دیگری استفاده شده است",
                "conflicts": [
                    {"protocol": row.protocol, "port": row.port}
                    for row in conflicts
                ],
            },
        )

    execution = "local" if getattr(node, "is_mother", False) else "ssh"
    conn = await asyncio.wait_for(connect_protocol_runtime(node, db), timeout=20)
    # Installing runtime packages over SSH can take minutes. Do not hold a
    # PostgreSQL transaction open throughout that external operation.
    db.expunge(node)
    db.commit()
    try:
        try:
            async with exclusive_node_install(node_id):
                result = await apply_profiles(conn, node, profiles)
        except NodeInstallBusy as exc:
            # Another request is already installing this node. Do not mark
            # healthy profiles as failed because the server is merely busy.
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            for key in protocols:
                _, _, _, port = resolved_by_key[key]
                _save_status(db, node, key, {
                    "ok": False,
                    "port": port,
                    "transport": PROTOCOL_CATALOG[key]["transport"],
                    "service": PROTOCOL_CATALOG[key]["core"],
                    "error": str(exc),
                })
            db.commit()
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "نصب/اعمال تنظیمات پروتکل ناموفق بود",
                    "error": str(exc)[:1800],
                },
            ) from exc

        failed: list[str] = []
        warning_map: dict[str, list[str]] = {}
        remaps = (result.get("core") or {}).get("port_remaps") or {}
        for key in protocols:
            health = dict(result["protocols"][key])
            preset, effective, warnings, requested_port = resolved_by_key[key]
            # The remote runtime can move a listener to a free port.
            # Config links and credential writers must see the applied port.
            remap = remaps.get(key) or {}
            applied_port = int(remap.get("to") or health.get("port") or requested_port)
            if not 1 <= applied_port <= 65535:
                raise RuntimeError("invalid runtime protocol port")
            if health.get("port") is not None and int(health["port"]) != applied_port:
                health["ok"] = False
                health["error"] = "runtime_reported_port_mismatch"
            health["port"] = applied_port
            _save_status(db, node, key, health)
            _save_setting(db, node.id, key, preset, effective, applied_port)
            warning_map[key] = warnings
            if not health.get("ok"):
                failed.append(key)
        db.commit()
        return {
            "ok": not failed,
            "node_id": node.id,
            "execution": execution,
            "core": result.get("core", {}),
            "protocols": result["protocols"],
            "warnings": warning_map,
            "failed_protocols": failed,
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/modern-protocols/{node_id}/health")
async def health(
    node_id: int,
    payload: ModernHealthV3In,
    db: Session = Depends(get_db),
):
    node = _protocol_node(db, node_id)
    rows = _status_rows(db, node.id)
    protocols = (
        _normalize_protocols(payload.protocols)
        if payload.protocols
        else [key for key in SINGBOX_PROTOCOLS if key in rows]
    )
    if not protocols:
        return {"ok": True, "node_id": node.id, "protocols": {}}
    unavailable = [key for key in protocols if key not in SINGBOX_PROTOCOLS]
    if unavailable:
        raise HTTPException(
            status_code=409,
            detail={"message": "Runtime adapter unavailable", "protocols": unavailable},
        )

    # Snapshot ORM values before network I/O. A remote node can be slow or
    # unresponsive; it must not hold an open PostgreSQL transaction meanwhile.
    ports = {
        key: int(rows[key].port) if key in rows and rows[key].port
        else int(PROTOCOL_CATALOG[key]["default_port"])
        for key in protocols
    }
    execution = "local" if getattr(node, "is_mother", False) else "ssh"
    conn = await asyncio.wait_for(connect_protocol_runtime(node, db), timeout=20)
    # The SSH connector has read NodeAccess by now. Detach node so accessing its
    # ID in _save_status won't implicitly start another transaction.
    db.expunge(node)
    db.commit()
    try:
        results: dict[str, Any] = {}
        for key in protocols:
            port = ports[key]
            try:
                result = await asyncio.wait_for(
                    profile_health(conn, key, port), timeout=15
                )
            except Exception as exc:
                result = {
                    "ok": False,
                    "protocol": key,
                    "port": port,
                    "transport": PROTOCOL_CATALOG[key]["transport"],
                    "service": PROTOCOL_CATALOG[key]["core"],
                    "error": (
                        "health_check_timeout"
                        if isinstance(exc, asyncio.TimeoutError)
                        else str(exc)
                    ),
                }
            results[key] = result
        # Complete all SSH calls before opening a database write transaction.
        try:
            pin = await asyncio.wait_for(certificate_pin(conn), timeout=15)
        except Exception:
            pin = None
        for key, result in results.items():
            _save_status(db, node, key, result)
        db.commit()
        return {
            "ok": all(item.get("ok") for item in results.values()),
            "node_id": node_id,
            "execution": execution,
            "certificate_public_key_sha256": pin,
            "protocols": results,
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.delete("/modern-protocols/{node_id}/{protocol}")
async def remove(
    node_id: int,
    protocol: str,
    db: Session = Depends(get_db),
):
    node = _protocol_node(db, node_id)
    key = str(protocol or "").strip().lower()
    if key not in PROTOCOL_CATALOG:
        raise HTTPException(status_code=422, detail="پروتکل معتبر نیست")
    if key not in SINGBOX_PROTOCOLS:
        raise HTTPException(status_code=409, detail="Runtime adapter این پروتکل فعال نیست")

    execution = "local" if getattr(node, "is_mother", False) else "ssh"
    conn = await asyncio.wait_for(connect_protocol_runtime(node, db), timeout=20)
    # Removal is remote I/O too: preserve the ORM data but close its read
    # transaction before waiting on SSH or systemd.
    db.expunge(node)
    db.commit()
    try:
        try:
            result = await remove_profile(conn, key)
        except (ModernRuntimeV2Error, Exception) as exc:
            raise HTTPException(
                status_code=502,
                detail={"message": "حذف پروتکل ناموفق بود", "error": str(exc)[:1800]},
            ) from exc
        status = (
            db.query(NodeProtocolConfig)
            .filter(
                NodeProtocolConfig.node_id == node.id,
                NodeProtocolConfig.protocol == key,
            )
            .first()
        )
        if status:
            status.status = "not_installed"
            status.last_error = None
            status.checked_at = datetime.utcnow()
        db.commit()
        return {
            **result,
            "node_id": node.id,
            "execution": execution,
        }
    finally:
        conn.close()
        await conn.wait_closed()
