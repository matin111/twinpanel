import base64
import shlex
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Node, NodeProtocolConfig, NodeType
from ..modern_protocol_runtime import (
    MODERN_PROTOCOL_SPECS,
    ModernProtocolError,
    certificate_pin,
    install_protocols,
    normalize_protocols,
    normalized_ports,
    protocol_health,
    remove_protocol,
    supported_protocols,
)
from ..mother_access import (
    generate_l2tp_psk,
    get_l2tp_psk,
    get_or_create_l2tp_psk,
    set_l2tp_psk,
)
from .provision import cmd, ssh_connect_saved


router = APIRouter(
    prefix="/v1/settings/vpn",
    tags=["vpn-settings"],
    dependencies=[Depends(require_admin)],
)


class L2tpPskUpdateIn(BaseModel):
    # TWINPANEL_FREE_L2TP_PSK_V1
    # Admin may choose letters, numbers and symbols.
    psk: str = Field(
        min_length=1,
        max_length=64,
    )


class ModernProtocolInstallIn(BaseModel):
    protocols: list[str]
    ports: dict[str, int] = Field(default_factory=dict)


class ModernProtocolHealthIn(BaseModel):
    protocols: list[str] | None = None


def _secret_file(psk: str) -> str:
    # TWINPANEL_L2TP_HEX_PSK_V1
    # strongSwan supports PSK as hexadecimal binary data.
    # This safely supports quotes, backslashes and other symbols
    # without breaking /etc/ipsec.secrets parsing.
    raw = str(psk).encode("utf-8")
    return f"%any %any : PSK 0x{raw.hex()}\n"


async def _apply_psk(
    db: Session,
    node: Node,
    psk: str,
) -> None:
    conn = None

    try:
        conn = await ssh_connect_saved(node, db)

        data = base64.b64encode(
            _secret_file(psk).encode()
        ).decode()

        await cmd(
            conn,
            (
                "tmp=$(mktemp); "
                f"printf '%s' {shlex.quote(data)} | "
                "base64 -d > \"$tmp\" && "
                "chmod 600 \"$tmp\" && "
                "cp -a /etc/ipsec.secrets "
                "/etc/ipsec.secrets.bak-twinpanel 2>/dev/null || true; "
                "cat \"$tmp\" > /etc/ipsec.secrets && "
                "rm -f \"$tmp\" && "
                "chmod 600 /etc/ipsec.secrets && "
                "(ipsec rereadsecrets || "
                "systemctl restart strongswan-starter || "
                "systemctl restart strongswan)"
            ),
            timeout=60,
        )

    finally:
        if conn:
            conn.close()
            await conn.wait_closed()


def _l2tp_exits(db: Session) -> list[Node]:
    return (
        db.query(Node).filter(Node.retired_at.is_(None))
        .filter(
            Node.node_type == NodeType.EXIT,
            Node.enable_l2tp.is_(True),
        )
        .order_by(Node.id.asc())
        .all()
    )


@router.get("/l2tp")
def get_l2tp_settings(
    db: Session = Depends(get_db),
):
    psk = get_or_create_l2tp_psk(db)
    nodes = _l2tp_exits(db)

    return {
        "psk": psk,
        "length": len(psk),
        "exit_count": len(nodes),
        "exit_nodes": [
            {
                "id": node.id,
                "name": node.name,
            }
            for node in nodes
        ],
    }


@router.post("/l2tp/generate")
def generate_l2tp_secret():
    psk = generate_l2tp_psk()

    return {
        "psk": psk,
        "length": len(psk),
    }


@router.put("/l2tp")
async def update_l2tp_settings(
    payload: L2tpPskUpdateIn,
    db: Session = Depends(get_db),
):
    new_psk = payload.psk.strip()

    if not new_psk:
        raise HTTPException(
            status_code=422,
            detail="IPsec Secret نمی‌تواند خالی باشد",
        )

    if "\n" in new_psk or "\r" in new_psk:
        raise HTTPException(
            status_code=422,
            detail="IPsec Secret نباید شامل خط جدید باشد",
        )
    old_psk = get_l2tp_psk(db)

    if not old_psk:
        old_psk = get_or_create_l2tp_psk(db)

    if new_psk == old_psk:
        return {
            "ok": True,
            "changed": False,
            "synced_nodes": [],
        }

    nodes = _l2tp_exits(db)

    succeeded: list[Node] = []
    failed: list[dict] = []

    for node in nodes:
        try:
            await _apply_psk(
                db,
                node,
                new_psk,
            )
            succeeded.append(node)

        except Exception as exc:
            failed.append({
                "id": node.id,
                "name": node.name,
                "error": str(exc),
            })

    if failed:
        rollback_failed: list[dict] = []

        for node in succeeded:
            try:
                await _apply_psk(
                    db,
                    node,
                    old_psk,
                )
            except Exception as exc:
                rollback_failed.append({
                    "id": node.id,
                    "name": node.name,
                    "error": str(exc),
                })

        raise HTTPException(
            status_code=502,
            detail={
                "message":
                    "اعمال Secret روی همه سرورها موفق نبود؛ تغییر لغو شد.",
                "failed_nodes": failed,
                "rollback_failed": rollback_failed,
            },
        )

    set_l2tp_psk(
        db,
        new_psk,
    )
    db.commit()

    return {
        "ok": True,
        "changed": True,
        "length": len(new_psk),
        "synced_nodes": [
            {
                "id": node.id,
                "name": node.name,
            }
            for node in succeeded
        ],
    }


# ============================================================
# TWINPANEL_MODERN_PROTOCOL_CORE_V1
# ============================================================

def _modern_exit(db: Session, node_id: int) -> Node:
    node = (
        db.query(Node)
        .filter(
            Node.id == node_id,
            Node.retired_at.is_(None),
        )
        .first()
    )
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    if node.node_type != NodeType.EXIT or node.agent_url == "local://core":
        raise HTTPException(
            status_code=400,
            detail="پروتکل‌های جدید فقط روی نود خروجی نصب می‌شوند",
        )
    return node


def _modern_cfg_rows(db: Session, node_id: int) -> dict[str, NodeProtocolConfig]:
    keys = list(MODERN_PROTOCOL_SPECS)
    rows = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == node_id,
            NodeProtocolConfig.protocol.in_(keys),
        )
        .all()
    )
    return {str(row.protocol): row for row in rows}


def _modern_cfg_payload(row: NodeProtocolConfig | None, key: str) -> dict[str, Any]:
    spec = MODERN_PROTOCOL_SPECS[key]
    return {
        "protocol": key,
        "name": spec.title,
        "core": "sing-box",
        "port": int(row.port) if row and row.port else spec.default_port,
        "transport": (row.transport if row and row.transport else spec.transport),
        "service": row.service_name if row and row.service_name else "twinpanel-sing-box",
        "status": row.status if row and row.status else "not_installed",
        "last_error": row.last_error if row else None,
        "checked_at": row.checked_at.isoformat() + "Z" if row and row.checked_at else None,
    }


def _save_modern_status(
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
    row.port = int(result.get("port") or MODERN_PROTOCOL_SPECS[key].default_port)
    row.port_text = str(row.port)
    row.transport = str(result.get("transport") or MODERN_PROTOCOL_SPECS[key].transport)
    row.service_name = "twinpanel-sing-box"
    row.status = "online" if result.get("ok") else "error"
    row.last_error = None if result.get("ok") else str(result.get("error") or "service_or_listener_unhealthy")[:1800]
    row.checked_at = datetime.utcnow()
    return row


@router.get("/modern-protocols")
def modern_protocol_inventory(db: Session = Depends(get_db)):
    nodes = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.node_type == NodeType.EXIT,
        )
        .order_by(Node.id.asc())
        .all()
    )
    payload = []
    for node in nodes:
        rows = _modern_cfg_rows(db, node.id)
        payload.append({
            "id": node.id,
            "name": node.name,
            "public_ip": node.public_ip,
            "public_domain": node.public_domain,
            "status": getattr(node.status, "value", str(node.status)),
            "protocols": [
                _modern_cfg_payload(rows.get(key), key)
                for key in MODERN_PROTOCOL_SPECS
            ],
        })
    return {
        "ok": True,
        "core": "sing-box",
        "supported_protocols": supported_protocols(),
        "nodes": payload,
    }


@router.post("/modern-protocols/{node_id}/install")
async def install_modern_protocols(
    node_id: int,
    payload: ModernProtocolInstallIn,
    db: Session = Depends(get_db),
):
    node = _modern_exit(db, node_id)
    try:
        protocols = normalize_protocols(payload.protocols)
        ports = normalized_ports(protocols, payload.ports)
    except ModernProtocolError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    selected_ports = set(ports.values())
    conflicts = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == node.id,
            NodeProtocolConfig.port.in_(selected_ports),
            ~NodeProtocolConfig.protocol.in_(protocols),
        )
        .all()
    )
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "یکی از پورت‌های انتخاب‌شده قبلاً توسط پروتکل دیگری ثبت شده است",
                "conflicts": [
                    {"protocol": row.protocol, "port": row.port}
                    for row in conflicts
                ],
            },
        )

    conn = await ssh_connect_saved(node, db)
    try:
        try:
            result = await install_protocols(conn, node, protocols, ports)
        except Exception as exc:
            for key in protocols:
                _save_modern_status(
                    db,
                    node,
                    key,
                    {
                        "ok": False,
                        "port": ports[key],
                        "transport": MODERN_PROTOCOL_SPECS[key].transport,
                        "error": str(exc),
                    },
                )
            db.commit()
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "نصب Core پروتکل‌های جدید ناموفق بود",
                    "error": str(exc)[:1800],
                },
            ) from exc

        failed = []
        for key in protocols:
            health = result["protocols"][key]
            _save_modern_status(db, node, key, health)
            if not health.get("ok"):
                failed.append(key)
        db.commit()
        return {
            "ok": not failed,
            "node_id": node.id,
            "core": result.get("core", {}),
            "protocols": result["protocols"],
            "failed_protocols": failed,
            "message": (
                "پروتکل‌های جدید نصب و Health Check شدند"
                if not failed
                else "Core نصب شد اما بعضی Listenerها سالم نیستند"
            ),
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/modern-protocols/{node_id}/health")
async def health_modern_protocols(
    node_id: int,
    payload: ModernProtocolHealthIn,
    db: Session = Depends(get_db),
):
    node = _modern_exit(db, node_id)
    rows = _modern_cfg_rows(db, node.id)
    try:
        protocols = (
            normalize_protocols(payload.protocols)
            if payload.protocols
            else [key for key in MODERN_PROTOCOL_SPECS if key in rows]
        )
    except ModernProtocolError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not protocols:
        return {"ok": True, "node_id": node.id, "protocols": {}}

    conn = await ssh_connect_saved(node, db)
    try:
        results: dict[str, Any] = {}
        for key in protocols:
            row = rows.get(key)
            port = int(row.port) if row and row.port else MODERN_PROTOCOL_SPECS[key].default_port
            try:
                result = await protocol_health(conn, key, port)
            except Exception as exc:
                result = {
                    "ok": False,
                    "protocol": key,
                    "port": port,
                    "transport": MODERN_PROTOCOL_SPECS[key].transport,
                    "error": str(exc),
                }
            results[key] = result
            _save_modern_status(db, node, key, result)
        pin = await certificate_pin(conn)
        db.commit()
        return {
            "ok": all(item.get("ok") for item in results.values()),
            "node_id": node.id,
            "certificate_public_key_sha256": pin,
            "protocols": results,
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.delete("/modern-protocols/{node_id}/{protocol}")
async def delete_modern_protocol(
    node_id: int,
    protocol: str,
    db: Session = Depends(get_db),
):
    node = _modern_exit(db, node_id)
    key = str(protocol or "").strip().lower()
    if key not in MODERN_PROTOCOL_SPECS:
        raise HTTPException(status_code=422, detail="پروتکل جدید معتبر نیست")

    conn = await ssh_connect_saved(node, db)
    try:
        try:
            result = await remove_protocol(conn, key)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail={"message": "حذف پروتکل ناموفق بود", "error": str(exc)[:1800]},
            ) from exc

        row = (
            db.query(NodeProtocolConfig)
            .filter(
                NodeProtocolConfig.node_id == node.id,
                NodeProtocolConfig.protocol == key,
            )
            .first()
        )
        if row:
            row.status = "disabled"
            row.last_error = None
            row.checked_at = datetime.utcnow()
            db.commit()
        return {
            "ok": True,
            "node_id": node.id,
            **result,
        }
    finally:
        conn.close()
        await conn.wait_closed()
