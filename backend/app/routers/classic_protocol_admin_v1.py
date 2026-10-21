from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import Node, NodeProtocolConfig, NodeType
from .provision import (
    ProtocolSettings,
    cmd,
    ensure_base,
    provision_protocols,
    ssh_connect_saved,
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


class EnsureClassicProtocolIn(BaseModel):
    node_id: int = Field(gt=0)
    protocol: ClassicProtocol
    port: int | None = Field(default=None, ge=1, le=65535)
    transport: Literal["udp", "tcp"] | None = None

    @model_validator(mode="after")
    def validate_protocol_options(self):
        if self.protocol == "l2tp" and self.port is not None:
            raise ValueError("L2TP/IPsec uses fixed UDP ports 500/4500/1701")
        if self.protocol != "openvpn" and self.transport is not None:
            raise ValueError("transport override is only supported for OpenVPN")
        return self


_DEFAULT_PORTS: dict[str, int] = {
    "cisco": 443,
    "openvpn": 1194,
    "wireguard": 51820,
    "v2ray": 8443,
}


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

    if protocol == "cisco":
        values["cisco_port"] = int(
            payload.port
            or (existing.port if existing and existing.port else 0)
            or _DEFAULT_PORTS[protocol]
        )

    elif protocol == "openvpn":
        values["openvpn_port"] = int(
            payload.port
            or (existing.port if existing and existing.port else 0)
            or _DEFAULT_PORTS[protocol]
        )
        saved_transport = str(
            existing.transport if existing else ""
        ).strip().lower()
        values["openvpn_transport"] = (
            payload.transport
            or (saved_transport if saved_transport in {"udp", "tcp"} else "udp")
        )

    elif protocol == "wireguard":
        values["wireguard_port"] = int(
            payload.port
            or (existing.port if existing and existing.port else 0)
            or _DEFAULT_PORTS[protocol]
        )

    elif protocol == "v2ray":
        values["xray_port"] = int(
            payload.port
            or (existing.port if existing and existing.port else 0)
            or _DEFAULT_PORTS[protocol]
        )

    return ProtocolSettings(**values)


@router.post("/ensure-classic-protocol")
async def ensure_classic_protocol(
    payload: EnsureClassicProtocolIn,
    db: Session = Depends(get_db),
):
    node = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == payload.node_id,
        )
        .first()
    )

    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")

    if node.node_type != NodeType.EXIT:
        raise HTTPException(
            status_code=422,
            detail="پروتکل‌های دسترسی فقط روی نود خروجی نصب می‌شوند",
        )

    existing = _existing_config(
        db,
        node.id,
        payload.protocol,
    )
    settings = _settings_for(payload, existing)

    conn = await ssh_connect_saved(node, db)
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
            "runtime": result,
            "enabled": bool(
                getattr(node, f"enable_{payload.protocol}", False)
            ),
            "message": "پروتکل با SSH ذخیره‌شده نصب/Repair و Health Check شد",
        }

    finally:
        conn.close()
        await conn.wait_closed()
