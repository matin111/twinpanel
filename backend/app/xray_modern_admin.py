from __future__ import annotations

import re
import shlex
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_admin
from .models import Node, NodeProtocolConfig, NodeType
from .routers import account_delivery, provision
from .xray_modern_runtime import (
    PROFILE_GRPC,
    PROFILE_HTTPUPGRADE,
    PROFILE_META,
    PROFILE_WS,
    PROFILE_XHTTP,
    _ensure_modern_xray,
    _enum_value,
    _public_port,
    _target_port,
)


router = APIRouter(
    prefix="/v1/xray-modern-admin",
    tags=["xray-modern-admin"],
    dependencies=[Depends(require_admin)],
)


_DOMAIN_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$"
)


class PrepareIn(BaseModel):
    domain: str | None = None
    issue_certificate: bool = True


class DomainIn(BaseModel):
    domain: str | None = None


def _clean_domain(value: Any) -> str:
    domain = str(value or "").strip().lower()
    domain = re.sub(r"^https?://", "", domain).split("/")[0].strip()

    if ":" in domain:
        domain = domain.split(":", 1)[0]

    if not domain:
        return ""

    if not _DOMAIN_RE.fullmatch(domain):
        raise HTTPException(
            status_code=422,
            detail="دامنه معتبر نیست",
        )

    return domain


def _node_or_404(
    db: Session,
    node_id: int,
) -> Node:
    node = (
        db.query(Node)
        .filter(
            Node.id == int(node_id),
            Node.retired_at.is_(None),
        )
        .first()
    )

    if not node:
        raise HTTPException(
            status_code=404,
            detail="سرور پیدا نشد",
        )

    if node.node_type != NodeType.EXIT:
        raise HTTPException(
            status_code=409,
            detail="Xray کاربر فقط روی نود خروجی پشتیبانی می‌شود",
        )

    return node


def _xray_cfg(
    db: Session,
    node_id: int,
) -> NodeProtocolConfig | None:
    return (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == int(node_id),
            NodeProtocolConfig.protocol == "v2ray",
        )
        .first()
    )


def _profile_rows(
    node: Node,
    base_port: int,
) -> list[dict[str, Any]]:
    rows = []

    for profile in (
        PROFILE_WS,
        PROFILE_XHTTP,
        PROFILE_HTTPUPGRADE,
        PROFILE_GRPC,
    ):
        meta = PROFILE_META[profile]

        rows.append(
            {
                "id": profile,
                "title": meta["title"],
                "security": meta["security"],
                "transport": meta["transport"],
                "recommended": bool(meta["recommended"]),
                "requires_tls_domain": profile in {
                    PROFILE_WS,
                    PROFILE_HTTPUPGRADE,
                },
                "target_port": _target_port(
                    base_port,
                    profile,
                ),
                "tunnel_public_port": _public_port(
                    node.id,
                    profile,
                ),
            }
        )

    return rows


def _node_payload(
    db: Session,
    node: Node,
) -> dict[str, Any]:
    cfg = _xray_cfg(db, node.id)
    base_port = int(
        getattr(cfg, "port", None)
        or account_delivery.DEFAULT_PORTS["v2ray"]
    )

    return {
        "id": int(node.id),
        "name": node.name,
        "public_ip": node.public_ip,
        "public_domain": (
            str(getattr(node, "public_domain", None) or "").strip()
            or None
        ),
        "enabled": bool(getattr(node, "enable_v2ray", False)),
        "status": _enum_value(getattr(cfg, "status", None)) if cfg else "missing",
        "base_port": base_port,
        "profiles": _profile_rows(node, base_port),
    }


async def _certificate_available(
    conn,
    domain: str,
) -> bool:
    quoted = shlex.quote(domain)

    command = f"""
DOMAIN={quoted}
for CERT in \
  /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
  /root/.acme.sh/${{DOMAIN}}_ecc/fullchain.cer \
  /root/.acme.sh/$DOMAIN/fullchain.cer
do
  [ -s \"$CERT\" ] || continue

  if openssl x509 \
      -checkend 86400 \
      -noout \
      -in \"$CERT\" >/dev/null 2>&1 \
    && openssl x509 \
      -checkhost \"$DOMAIN\" \
      -noout \
      -in \"$CERT\" >/dev/null 2>&1
  then
    echo READY
    break
  fi
done
"""

    result = await provision.cmd(
        conn,
        command,
        check=False,
    )

    return "READY" in str(result).splitlines()


async def _resolve_domain_ips(
    conn,
    domain: str,
) -> set[str]:
    result = await provision.cmd(
        conn,
        (
            f"getent ahostsv4 {shlex.quote(domain)} 2>/dev/null "
            "| awk '{print $1}' | sort -u"
        ),
        check=False,
    )

    return {
        line.strip()
        for line in str(result).splitlines()
        if line.strip()
    }


async def _issue_certificate(
    conn,
    node: Node,
    domain: str,
) -> None:
    resolved = await _resolve_domain_ips(
        conn,
        domain,
    )

    if str(node.public_ip).strip() not in resolved:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "DNS دامنه هنوز به IP همین نود خروجی اشاره نمی‌کند",
                "domain": domain,
                "expected_ip": node.public_ip,
                "resolved_ips": sorted(resolved),
            },
        )

    occupied = (
        await provision.cmd(
            conn,
            (
                "ss -H -lntp 2>/dev/null "
                "| awk '$4 ~ /:80$/ {print; exit}'"
            ),
            check=False,
        )
    ).strip()

    if occupied:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "پورت 80 روی نود اشغال است؛ برای صدور خودکار SSL "
                    "هیچ سرویس موجودی متوقف نشد"
                ),
                "listener": occupied[:500],
            },
        )

    await provision.cmd(
        conn,
        (
            "if ! command -v curl >/dev/null 2>&1 "
            "|| ! command -v openssl >/dev/null 2>&1 "
            "|| ! command -v socat >/dev/null 2>&1; then "
            "export DEBIAN_FRONTEND=noninteractive; "
            "apt-get -o DPkg::Lock::Timeout=300 update -y >/dev/null 2>&1; "
            "apt-get -o DPkg::Lock::Timeout=300 install -y "
            "curl openssl socat >/dev/null; "
            "fi"
        ),
        timeout=600,
    )

    if not await _certificate_available(
        conn,
        domain,
    ):
        await provision.ufw_allow(
            conn,
            80,
            "tcp",
        )

        await provision.cmd(
            conn,
            (
                "if [ ! -x /root/.acme.sh/acme.sh ]; then "
                "curl -fsSL https://get.acme.sh "
                "| sh >/dev/null; "
                "fi; "
                "/root/.acme.sh/acme.sh "
                "--issue --standalone "
                f"-d {shlex.quote(domain)} "
                "--keylength ec-256 "
                "--server letsencrypt"
            ),
            timeout=600,
        )

    if not await _certificate_available(
        conn,
        domain,
    ):
        raise RuntimeError(
            "گواهی SSL معتبر بعد از صدور پیدا نشد"
        )


async def _status_remote(
    conn,
    base_port: int,
) -> dict[str, Any]:
    raw_state = await provision.cmd(
        conn,
        (
            "if [ -s /usr/local/etc/xray/twinpanel-modern-state.json ]; "
            "then cat /usr/local/etc/xray/twinpanel-modern-state.json; "
            "else echo '{}'; fi"
        ),
        check=False,
    )

    try:
        state = __import__("json").loads(
            str(raw_state or "{}")
        )
    except Exception:
        state = {}

    listeners: dict[str, bool] = {}

    for profile in (
        PROFILE_XHTTP,
        PROFILE_GRPC,
        PROFILE_WS,
        PROFILE_HTTPUPGRADE,
    ):
        port = _target_port(
            base_port,
            profile,
        )

        listeners[profile] = bool(
            await provision.listener(
                conn,
                port,
                "tcp",
            )
        )

    return {
        "service_active": await provision.active(
            conn,
            "xray",
        ),
        "tls_enabled": bool(state.get("tls_enabled")),
        "tls_domain": state.get("tls_domain") or None,
        "profiles": listeners,
    }


@router.get("/nodes")
def list_xray_nodes(
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.node_type == NodeType.EXIT,
        )
        .order_by(Node.id.asc())
        .all()
    )

    return {
        "ok": True,
        "nodes": [
            _node_payload(db, node)
            for node in rows
            if bool(getattr(node, "enable_v2ray", False))
            or _xray_cfg(db, node.id) is not None
        ],
    }


@router.put("/nodes/{node_id}/domain")
def save_xray_domain(
    node_id: int,
    payload: DomainIn,
    db: Session = Depends(get_db),
):
    node = _node_or_404(
        db,
        node_id,
    )

    domain = _clean_domain(
        payload.domain
    )

    node.public_domain = (
        domain
        or None
    )

    db.commit()
    db.refresh(node)

    return {
        "ok": True,
        "node": _node_payload(db, node),
    }


@router.get("/nodes/{node_id}/status")
async def xray_node_status(
    node_id: int,
    db: Session = Depends(get_db),
):
    node = _node_or_404(
        db,
        node_id,
    )

    cfg = _xray_cfg(
        db,
        node.id,
    )

    if not cfg:
        raise HTTPException(
            status_code=409,
            detail="Xray هنوز روی این نود Provision نشده است",
        )

    conn = await account_delivery.ssh_connect_saved(
        node,
        db,
    )

    try:
        return {
            "ok": True,
            "node": _node_payload(db, node),
            "runtime": await _status_remote(
                conn,
                int(cfg.port or account_delivery.DEFAULT_PORTS["v2ray"]),
            ),
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/nodes/{node_id}/prepare")
async def prepare_xray_node(
    node_id: int,
    payload: PrepareIn,
    db: Session = Depends(get_db),
):
    node = _node_or_404(
        db,
        node_id,
    )

    cfg = _xray_cfg(
        db,
        node.id,
    )

    if not cfg or _enum_value(cfg.status) != "online":
        raise HTTPException(
            status_code=409,
            detail="Xray پایه روی این نود آنلاین نیست",
        )

    domain = _clean_domain(
        payload.domain
        if payload.domain is not None
        else getattr(node, "public_domain", None)
    )

    if payload.domain is not None:
        node.public_domain = domain or None
        db.commit()
        db.refresh(node)

    conn = await account_delivery.ssh_connect_saved(
        node,
        db,
    )

    try:
        if domain and payload.issue_certificate:
            if not await _certificate_available(
                conn,
                domain,
            ):
                await _issue_certificate(
                    conn,
                    node,
                    domain,
                )

        state = await _ensure_modern_xray(
            conn,
            int(cfg.port or account_delivery.DEFAULT_PORTS["v2ray"]),
            node,
        )

        runtime = await _status_remote(
            conn,
            int(cfg.port or account_delivery.DEFAULT_PORTS["v2ray"]),
        )

        return {
            "ok": True,
            "node": _node_payload(db, node),
            "runtime": runtime,
            "available_profiles": state.get("available_profiles") or [],
            "message": (
                "پروفایل‌های امن Xray آماده شدند"
                if runtime.get("tls_enabled")
                else (
                    "XHTTP REALITY و gRPC REALITY آماده شدند؛ "
                    "برای WebSocket TLS باید دامنه و SSL معتبر تنظیم شود"
                )
            ),
        }

    finally:
        conn.close()
        await conn.wait_closed()
