from __future__ import annotations

import json
import re
import shlex
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import get_db
from .deps import require_admin
from .models import Node, NodeProtocolConfig, NodeType
from .routers import account_delivery, provision
from .xray_modern_runtime import (

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
                    "XHTTP REALITY آماده شد؛ "
                    "برای WebSocket TLS باید دامنه و SSL معتبر تنظیم شود"
                )
            ),
        }

    finally:
        conn.close()
        await conn.wait_closed()


# TWINPANEL_XRAY_ADMIN_INBOUND_EDITOR_V1
# 3x-ui-inspired controls: one node-level draft for all future subscriptions.
# Saving does NOT activate settings; actual server apply + health check must
# precede publishing any SNI overrides. Never mutate per-user credentials here.
_XRAY_TRANSPORTS = frozenset({"tcp", "ws", "xhttp", "httpupgrade"})
_XRAY_SECURITIES = frozenset({"tls", "reality"})


class InboundEditorDraft(BaseModel):
    connection_domain: str | None = None
    tls_server_name: str | None = None
    reality_server_name: str | None = None
    reality_target: str | None = None
    transport: str = "tcp"
    security: str = "tls"
    inbounds: dict[str, dict[str, str]] | None = None


def _validated_editor_settings(payload: InboundEditorDraft) -> dict[str, str]:
    def hostname(value: str | None) -> str:
        raw = str(value or "").strip().lower()
        if not raw:
            return ""
        if len(raw) > 253 or ".." in raw or any(len(x) > 63 for x in raw.split(".")):
            raise HTTPException(status_code=422, detail="Invalid domain length")
        if not _DOMAIN_RE.fullmatch(raw):
            raise HTTPException(status_code=422, detail="Invalid domain")
        return raw

    transport = payload.transport.strip().lower()
    security = payload.security.strip().lower()
    if transport not in _XRAY_TRANSPORTS or security not in _XRAY_SECURITIES:
        raise HTTPException(status_code=422, detail="Unsupported transport/security")
    if security == "reality" and transport not in {"xhttp", "tcp"}:
        raise HTTPException(status_code=422, detail="REALITY transport is incompatible")

    target = str(payload.reality_target or "").strip().lower()
    if target:
        if target.count(":") != 1 or not target.endswith(":443"):
            raise HTTPException(status_code=422, detail="REALITY target must be hostname:443")
        hostname(target.rsplit(":", 1)[0])
    inbounds: dict[str, dict[str, str]] = {}
    for key, expected_transport, expected_security in (
        ("tcp_tls", "tcp", "tls"),
        ("ws_tls", "ws", "tls"),
        ("xhttp_reality", "xhttp", "reality"),
    ):
        entry = (payload.inbounds or {}).get(key) or {}
        if not isinstance(entry, dict):
            raise HTTPException(status_code=422, detail=f"Invalid inbound {key}")
        if entry and (
            str(entry.get("transport") or expected_transport) != expected_transport
            or str(entry.get("security") or expected_security) != expected_security
        ):
            raise HTTPException(status_code=422, detail=f"Inbound {key} transport/security mismatch")
        server_name = hostname(entry.get("server_name"))
        connection_domain = hostname(entry.get("connection_domain"))
        path = str(entry.get("path") or "").strip()
        if path and (not path.startswith("/") or len(path) > 256 or any(ord(char) < 32 for char in path)):
            raise HTTPException(status_code=422, detail=f"Invalid inbound path: {key}")
        target = str(entry.get("target") or "").strip().lower()
        if target:
            if key != "xhttp_reality" or not target.endswith(":443") or target.count(":") != 1:
                raise HTTPException(status_code=422, detail=f"Invalid REALITY target: {key}")
            hostname(target.rsplit(":", 1)[0])
        if key == "xhttp_reality" and server_name and target and target != server_name + ":443":
            raise HTTPException(status_code=422, detail="REALITY serverName and target must match")
        inbounds[key] = {
            "connection_domain": connection_domain,
            "server_name": server_name,
            "path": path,
            "target": target,
            "transport": expected_transport,
            "security": expected_security,
        }
    if payload.inbounds and inbounds["xhttp_reality"]["server_name"]:
        # Maintain compatibility with existing verified REALITY Apply endpoint.
        payload.reality_server_name = inbounds["xhttp_reality"]["server_name"]
        payload.reality_target = inbounds["xhttp_reality"]["target"]

    return {
        "inbounds": inbounds,
        "connection_domain": hostname(payload.connection_domain),
        "tls_server_name": hostname(payload.tls_server_name),
        "reality_server_name": hostname(payload.reality_server_name),
        "reality_target": target,
        "transport": transport,
        "security": security,
    }


@router.get("/nodes/{node_id}/inbound-editor")
async def get_xray_inbound_editor(node_id: int, db: Session = Depends(get_db)):
    node = _node_or_404(db, node_id)
    row = db.execute(
        text(
            "SELECT settings_json FROM modern_protocol_settings "
            "WHERE node_id=:node_id AND protocol='v2ray'"
        ), {"node_id": int(node_id)}
    ).scalar_one_or_none()
    try:
        values = json.loads(row) if row else {}
    except (ValueError, TypeError):
        values = {}
    if not isinstance(values, dict):
        values = {}
    runtime_state: dict[str, Any] = {}
    # Fetch the installed runtime defaults from the selected node. Do not
    # fabricate "/" paths, rotate keys, or provision a customer on UI GET.
    conn = None
    try:
        conn = await account_delivery.ssh_connect_saved(node, db)
        raw = await provision.cmd(
            conn,
            "cat /usr/local/etc/xray/twinpanel-modern-state.json",
            timeout=8,
        )
        runtime_state = json.loads(raw)
        if not isinstance(runtime_state, dict):
            runtime_state = {}
    except Exception:
        runtime_state = {}
    finally:
        if conn is not None:
            conn.close()
            await conn.wait_closed()
    default_domain = str(getattr(node, "xray_domain", None) or getattr(node, "public_domain", None) or "")
    applied_profiles = values.get("inbound_applied") or {}
    if not isinstance(applied_profiles, dict):
        applied_profiles = {}
    tcp_applied = applied_profiles.get("tcp_tls") or {}
    ws_applied = applied_profiles.get("ws_tls") or {}
    xhttp_applied = applied_profiles.get("xhttp_reality") or {}
    return {
        "node_id": int(node.id),
        "defaults": {
            "connection_domain": default_domain,
            "tls_server_name": str(runtime_state.get("tls_domain") or default_domain),
            "reality_server_name": str(runtime_state.get("reality_server_name") or values.get("reality_server_name") or ""),
            "reality_target": str(runtime_state.get("reality_target") or values.get("reality_target") or ""),
            "transport": "tcp",
            "security": "tls",
            "inbounds": {
                "tcp_tls": {
                    "connection_domain": str(tcp_applied.get("connection_domain") or default_domain),
                    "server_name": str(runtime_state.get("tls_sni_tcp") or tcp_applied.get("server_name") or runtime_state.get("tls_domain") or default_domain),
                    "path": "", "target": "", "transport": "tcp", "security": "tls",
                },
                "ws_tls": {
                    "connection_domain": str(ws_applied.get("connection_domain") or default_domain),
                    "server_name": str(runtime_state.get("tls_sni_ws") or ws_applied.get("server_name") or runtime_state.get("tls_domain") or default_domain),
                    "path": str(runtime_state.get("ws_path") or ((values.get("inbound_applied") or {}).get("ws_tls") or {}).get("path") or ""), "target": "", "transport": "ws", "security": "tls",
                },
                "xhttp_reality": {
                    "connection_domain": str(xhttp_applied.get("connection_domain") or default_domain),
                    "server_name": str(runtime_state.get("reality_server_name") or values.get("reality_server_name") or ""),
                    "path": str(runtime_state.get("xhttp_path") or ((values.get("inbound_applied") or {}).get("xhttp_reality") or {}).get("path") or ""), "target": str(runtime_state.get("reality_target") or values.get("reality_target") or ""),
                    "transport": "xhttp", "security": "reality",
                },
            },
        },
        "draft": values.get("draft") if isinstance(values.get("draft"), dict) else None,
        "applied": {
            key: values[key] for key in ("reality_server_name", "tls_server_name")
            if isinstance(values.get(key), str)
        },
        "transports": sorted(_XRAY_TRANSPORTS),
        "securities": sorted(_XRAY_SECURITIES),
        "requires_apply": True,
        "runtime_detected": bool(runtime_state),
        "message": "Saving a draft never modifies Xray or customer links.",
    }


@router.put("/nodes/{node_id}/inbound-editor")
def save_xray_inbound_editor_draft(
    node_id: int,
    payload: InboundEditorDraft,
    db: Session = Depends(get_db),
):
    _node_or_404(db, node_id)
    draft = _validated_editor_settings(payload)
    # Merge with existing applied data, never replace it on a draft edit.
    row = db.execute(
        text(
            "SELECT settings_json FROM modern_protocol_settings "
            "WHERE node_id=:node_id AND protocol='v2ray' FOR UPDATE"
        ), {"node_id": int(node_id)}
    ).scalar_one_or_none()
    try:
        settings = json.loads(row) if row else {}
    except (ValueError, TypeError):
        settings = {}
    if not isinstance(settings, dict):
        settings = {}
    settings["draft"] = draft
    data = json.dumps(settings, ensure_ascii=False, separators=(",", ":"))
    db.execute(
        text(
            "INSERT INTO modern_protocol_settings "
            "(node_id, protocol, preset_name, settings_json, schema_version, created_at, updated_at) "
            "VALUES (:node_id, 'v2ray', 'custom', :settings, 1, :now, :now) "
            "ON CONFLICT (node_id, protocol) DO UPDATE SET "
            "settings_json=EXCLUDED.settings_json, updated_at=EXCLUDED.updated_at"
        ),
        {"node_id": int(node_id), "settings": data, "now": datetime.utcnow()},
    )
    db.commit()
    return {"ok": True, "node_id": int(node_id), "draft": draft, "applied": False}


# TWINPANEL_XRAY_INBOUND_EDITOR_APPLY_V1
# Apply only REALITY target/SNI after validating against the active Xray.
# Existing connection routes, keys, credentials, and TLS profiles stay intact.
_XRAY_REALITY_APPLY_SCRIPT = r'''
import json
import ssl
import socket
import os
import shutil
import subprocess
import fcntl
import stat
from pathlib import Path

root = Path("/usr/local/etc/xray")
config_path = root / "config.json"
state_path = root / "twinpanel-modern-state.json"
target = __TARGET__
name = __NAME__
ws_path = __WS_PATH__
xhttp_path = __XHTTP_PATH__
tcp_tls_sni = __TCP_TLS_SNI__
ws_tls_sni = __WS_TLS_SNI__
lock = open("/run/lock/twinpanel-xray-inbound-editor.lock", "a+")
fcntl.flock(lock, fcntl.LOCK_EX)
host, port = target.rsplit(":", 1)
if host != name or port != "443":
    raise RuntimeError("REALITY target and serverName must match")
with socket.create_connection((host, 443), timeout=7) as sock:
    with ssl.create_default_context().wrap_socket(sock, server_hostname=name) as tls:
        if tls.version() != "TLSv1.3":
            raise RuntimeError("REALITY target requires TLS 1.3")
config = json.loads(config_path.read_text())
state = json.loads(state_path.read_text())
inbounds = [
    entry for entry in config.get("inbounds", [])
    if entry.get("tag") == "vless-xhttp-reality"
]
if len(inbounds) != 1:
    raise RuntimeError("Missing XHTTP REALITY inbound")
for entry in inbounds:
    settings = entry["streamSettings"]
    if settings.get("security") != "reality":
        raise RuntimeError("REALITY inbound security mismatch")
    reality = settings["realitySettings"]
    if not reality.get("privateKey") or not reality.get("shortIds"):
        raise RuntimeError("Existing REALITY keys are missing")
    reality["target"] = target
    # A previously published REALITY URI may still use the old SNI. Keep its
    # name in the allowed list until subscribers update; credentials, keys,
    # XHTTP path, ports and the public endpoint remain unchanged.
    old_names = reality.get("serverNames") or []
    legacy_names = state.get("reality_legacy_server_names") or []
    aliases = []
    import re
    for candidate in [*old_names, *legacy_names]:
        candidate = str(candidate or "").strip().lower()
        if (
            candidate and candidate != name
            and len(candidate) <= 253 and "." in candidate and ".." not in candidate
            and re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])", candidate)
            and candidate not in aliases
        ):
            aliases.append(candidate)
        if len(aliases) >= 4:
            break
    reality["serverNames"] = [name, *aliases]
state["reality_target"] = target
state["reality_server_name"] = name
state["reality_legacy_server_names"] = aliases
# TLS SNI may change only when the currently installed certificate covers it.
for tag, server_name, state_key in (
    ("vless-tcp-tls", tcp_tls_sni, "tls_sni_tcp"),
    ("vless-ws-tls", ws_tls_sni, "tls_sni_ws"),
):
    if not server_name:
        continue
    entries = [x for x in config["inbounds"] if x.get("tag") == tag]
    if len(entries) != 1:
        raise RuntimeError("TLS inbound is missing: " + tag)
    stream = entries[0]["streamSettings"]
    tls_settings = stream["tlsSettings"]
    certificates = tls_settings.get("certificates") or []
    if not certificates:
        raise RuntimeError("No managed TLS certificate for " + tag)
    certificate = certificates[0].get("certificateFile")
    if not certificate or not os.path.isfile(certificate):
        raise RuntimeError("TLS certificate unavailable")
    result = subprocess.run(
        ["openssl", "x509", "-noout", "-checkhost", server_name, "-in", certificate],
        capture_output=True, timeout=10,
    )
    if result.returncode:
        raise RuntimeError("TLS certificate does not cover SNI " + server_name)
    tls_settings["serverName"] = server_name
    state[state_key] = server_name
# Apply path changes to matching listeners and persisted state, preserving UUIDs.
if ws_path:
    matches = [entry for entry in config["inbounds"] if entry.get("tag") == "vless-ws-tls"]
    if len(matches) != 1 or matches[0].get("streamSettings", {}).get("network") != "ws":
        raise RuntimeError("WebSocket TLS inbound missing")
    matches[0]["streamSettings"]["wsSettings"]["path"] = ws_path
    state["ws_path"] = ws_path
if xhttp_path:
    matches = [entry for entry in config["inbounds"] if entry.get("tag") == "vless-xhttp-reality"]
    if len(matches) != 1:
        raise RuntimeError("XHTTP REALITY inbound missing")
    matches[0]["streamSettings"]["xhttpSettings"]["path"] = xhttp_path
    state["xhttp_path"] = xhttp_path
stamp = str(os.getpid())
backups = []
stages = []
original_modes = {}
try:
    if subprocess.run(
        ["systemctl", "is-active", "--quiet", "xray"], timeout=10,
    ).returncode != 0:
        raise RuntimeError("Xray must be active before applying an inbound edit")
    for path, doc in ((config_path, config), (state_path, state)):
        metadata = path.stat()
        original_modes[path] = metadata
        backup = path.with_name(path.name + ".pre-inbound-apply-" + stamp)
        shutil.copy2(path, backup)
        os.chmod(backup, 0o600)
        backups.append((path, backup))
        stage = path.with_name(path.stem + ".inbound-" + stamp + ".json")
        stage.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
        # Preserve Xray service-user access, including dedicated service groups.
        os.chown(stage, metadata.st_uid, metadata.st_gid)
        os.chmod(stage, stat.S_IMODE(metadata.st_mode))
        stages.append(stage)
    result = subprocess.run(
        ["/usr/local/bin/xray", "run", "-test", "-config", str(stages[0])],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode:
        raise RuntimeError("Xray configuration validation failed: " + result.stderr[-400:])
    for (path, _), stage in zip(backups, stages):
        os.replace(stage, path)
    subprocess.run(["systemctl", "restart", "xray"], check=True, timeout=20)
    state_check = subprocess.run(["systemctl", "is-active", "--quiet", "xray"], timeout=10)
    if state_check.returncode:
        raise RuntimeError("Xray did not become active")
    new_config = json.loads(config_path.read_text())
    assert all(
        x["streamSettings"]["realitySettings"]["serverNames"] == [name]
        for x in new_config["inbounds"] if x.get("tag") in
        ("vless-xhttp-reality",)
    )
except Exception:
    for path, backup in backups:
        if backup.exists():
            os.replace(backup, path)
            metadata = original_modes[path]
            os.chown(path, metadata.st_uid, metadata.st_gid)
            os.chmod(path, stat.S_IMODE(metadata.st_mode))
    if backups:
        subprocess.run(["systemctl", "restart", "xray"], capture_output=True, timeout=20)
    raise
finally:
    for stage in stages:
        stage.unlink(missing_ok=True)
print(json.dumps({"ok": True, "reality_server_name": name, "reality_target": target}))
'''


@router.post("/nodes/{node_id}/inbound-editor/apply")
async def apply_xray_inbound_editor(node_id: int, db: Session = Depends(get_db)):
    import asyncio
    import base64

    node = _node_or_404(db, node_id)
    row = db.execute(
        text(
            "SELECT settings_json FROM modern_protocol_settings "
            "WHERE node_id=:node_id AND protocol='v2ray'"
        ), {"node_id": int(node_id)}
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=409, detail="No saved inbound draft")
    settings = json.loads(row)
    draft = settings.get("draft")
    if not isinstance(draft, dict):
        raise HTTPException(status_code=409, detail="No valid inbound draft")
    candidate = _validated_editor_settings(InboundEditorDraft(**draft))
    # Current production supports these TLS and REALITY profiles, not an
    # arbitrary transport conversion. Reject rather than publishing broken URIs.
    if (candidate["transport"], candidate["security"]) not in {
        ("tcp", "tls"), ("ws", "tls"), ("httpupgrade", "tls"),
        ("xhttp", "reality"),
    }:
        raise HTTPException(status_code=422, detail="Transport/security not provisioned")
    name = candidate["reality_server_name"]
    target = candidate["reality_target"]
    inbounds = candidate.get("inbounds") or {}
    ws_profile = inbounds.get("ws_tls") or {}
    xhttp_profile = inbounds.get("xhttp_reality") or {}
    ws_path = str(ws_profile.get("path") or "")
    xhttp_path = str(xhttp_profile.get("path") or "")
    tcp_tls_sni = str((inbounds.get("tcp_tls") or {}).get("server_name") or "")
    ws_tls_sni = str(ws_profile.get("server_name") or "")
    # DNS aliases may be changed without altering any server listener, but
    # only if they resolve to the same ingress address as the existing domain.
    import socket

    expected_domain = str(
        getattr(node, "xray_domain", None)
        or getattr(node, "public_domain", None)
        or getattr(node, "public_ip", None)
        or ""
    ).strip().lower()

    def _resolved_addresses(domain: str) -> set[str]:
        return {
            item[4][0] for item in socket.getaddrinfo(
                domain, None, type=socket.SOCK_STREAM
            )
        }

    alias_changes: dict[str, str] = {}
    for profile_key in ("tcp_tls", "ws_tls", "xhttp_reality"):
        alias = str((inbounds.get(profile_key) or {}).get("connection_domain") or "").strip().lower()
        if not alias or alias == expected_domain:
            continue
        if not expected_domain:
            raise HTTPException(status_code=422, detail="Cannot verify existing ingress domain")
        try:
            expected_ips = await asyncio.wait_for(
                asyncio.to_thread(_resolved_addresses, expected_domain), timeout=5
            )
            new_ips = await asyncio.wait_for(
                asyncio.to_thread(_resolved_addresses, alias), timeout=5
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise HTTPException(status_code=422, detail="DNS alias validation failed") from exc
        if not new_ips or not expected_ips or not new_ips.issubset(expected_ips):
            raise HTTPException(status_code=422, detail="Connection domain must resolve to the current ingress")
        alias_changes[profile_key] = alias
    # Published path changes require a valid, non-root path. The node keeps
    # its existing path if no explicit value was supplied.
    for path_value in (ws_path, xhttp_path):
        if path_value and (path_value == "/" or len(path_value) < 8):
            raise HTTPException(status_code=422, detail="Use a unique path of at least 8 characters")
    if not name or not target or target != name + ":443":
        raise HTTPException(status_code=422, detail="REALITY name and target must match on :443")

    conn = await account_delivery.ssh_connect_saved(node, db)
    try:
        script = _XRAY_REALITY_APPLY_SCRIPT.replace(
            "__TARGET__", json.dumps(target)
        ).replace("__NAME__", json.dumps(name)).replace(
            "__WS_PATH__", json.dumps(ws_path)
        ).replace("__XHTTP_PATH__", json.dumps(xhttp_path)).replace(
            "__TCP_TLS_SNI__", json.dumps(tcp_tls_sni)
        ).replace("__WS_TLS_SNI__", json.dumps(ws_tls_sni))
        encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
        command = (
            "python3 -c "
            + shlex.quote("import base64;exec(base64.b64decode(" + repr(encoded) + "))")
        )
        result = await provision.cmd(conn, command, timeout=55)
        report = json.loads(result.splitlines()[-1])
        if not report.get("ok"):
            raise RuntimeError("REALITY verification did not succeed")
    finally:
        conn.close()
        await conn.wait_closed()

    # Publish the verified server settings atomically to the central feed.
    # Only the REALITY field is enabled: TLS, domain routing and transport
    # remain drafts until corresponding server-side apply is implemented.
    settings["reality_server_name"] = name
    settings["reality_target"] = target
    settings["inbound_applied"] = {
        **(settings.get("inbound_applied") or {}),
        "tcp_tls": {
            **((settings.get("inbound_applied") or {}).get("tcp_tls") or {}),
            **({"server_name": tcp_tls_sni} if tcp_tls_sni else {}),
            **({"connection_domain": alias_changes["tcp_tls"]} if "tcp_tls" in alias_changes else {}),
        },
        "ws_tls": {
            **((settings.get("inbound_applied") or {}).get("ws_tls") or {}),
            **({"path": ws_path} if ws_path else {}),
            **({"server_name": ws_tls_sni} if ws_tls_sni else {}),
            **({"connection_domain": alias_changes["ws_tls"]} if "ws_tls" in alias_changes else {}),
        },
        "xhttp_reality": {
            **((settings.get("inbound_applied") or {}).get("xhttp_reality") or {}),
            **({"path": xhttp_path} if xhttp_path else {}),
            "server_name": name, "target": target,
            **({"connection_domain": alias_changes["xhttp_reality"]} if "xhttp_reality" in alias_changes else {}),
        },
    }
    settings["last_verified_at"] = datetime.utcnow().isoformat() + "Z"
    db.execute(
        text(
            "UPDATE modern_protocol_settings SET settings_json=:settings, "
            "updated_at=:now WHERE node_id=:node_id AND protocol='v2ray'"
        ),
        {
            "node_id": int(node_id),
            "settings": json.dumps(settings, ensure_ascii=False),
            "now": datetime.utcnow(),
        },
    )
    db.commit()
    return {
        "ok": True, "node_id": int(node_id),
        "applied_fields": ["reality_server_name", "reality_target"] + (["ws_path"] if ws_path else []) + (["xhttp_path"] if xhttp_path else []) + (["tcp_tls_sni"] if tcp_tls_sni else []) + (["ws_tls_sni"] if ws_tls_sni else []) + (["connection_domain"] if alias_changes else []),
        "reality_server_name": name,
        "note": "Validated TLS SNI, paths and same-ingress DNS aliases applied; transport types unchanged.",
    }
