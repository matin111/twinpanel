from __future__ import annotations

import ipaddress
import shlex
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..dnstt_artifact import stage_dnstt_binary
from ..dns_emergency_iran_models import DnsEmergencyIranSetting
from ..models import Node, NodeType, Tunnel, TunnelStatus
from .dns_emergency import (
    BINARY_PATH,
    DNSTT_COMMIT,
    DNSTT_REPOSITORY,
    GO_VERSION,
    _candidate_rows,
    _connect,
    _listen_addr,
    _normalize_domain,
    _parse_lines,
    _run_script,
)


router = APIRouter(
    prefix="/v1/settings/vpn",
    tags=["dns-emergency-iran"],
    dependencies=[Depends(require_admin)],
)

SERVICE_NAME = "twinpanel-dnstt-iran.service"
STATE_DIR = "/etc/twinpanel/dnstt-iran"


class DnsEmergencyIranInstallIn(BaseModel):
    tunnel_id: int = Field(gt=0)
    exit_node_id: int = Field(gt=0)
    tunnel_domain: str = Field(min_length=4, max_length=253)
    nameserver_host: str | None = Field(default=None, max_length=253)
    upstream_port: int = Field(ge=1, le=65535)


def _node(db: Session, node_id: int, node_type: NodeType) -> Node:
    node = (
        db.query(Node)
        .filter(Node.id == int(node_id), Node.retired_at.is_(None))
        .first()
    )
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    if node.node_type != node_type:
        label = "ایران" if node_type == NodeType.IRAN else "خارج"
        raise HTTPException(status_code=400, detail=f"نود انتخاب‌شده باید از نوع {label} باشد")
    try:
        ipaddress.ip_address(str(node.public_ip))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Public IP نود معتبر نیست") from exc
    return node


def _setting(db: Session, iran_node_id: int) -> DnsEmergencyIranSetting | None:
    return (
        db.query(DnsEmergencyIranSetting)
        .filter(DnsEmergencyIranSetting.iran_node_id == int(iran_node_id))
        .first()
    )


def _host_address(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise RuntimeError("tunnel_runtime_address_missing")
    try:
        if "/" in raw:
            return str(ipaddress.ip_interface(raw).ip)
        return str(ipaddress.ip_address(raw))
    except ValueError as exc:
        raise RuntimeError(f"tunnel_runtime_address_invalid:{raw}") from exc


def _tunnel_addresses(tunnel_id: int) -> tuple[str, str, str]:
    """Use the same active-L3 runtime address source as the tunnel core.

    The tunnels module is monkeypatched by active_l3_route_binding_v94 during
    application startup. Resolving its helper at call time keeps DNS Emergency
    aligned with the actually selected carrier (TP27 Fast, MASQUE, etc.) rather
    than rebuilding the legacy 10.64.x.x subnet independently.
    """

    from . import tunnels as tunnel_router

    network, iran_value, exit_value = tunnel_router._tunnel_addresses(int(tunnel_id))
    return str(network), _host_address(str(iran_value)), _host_address(str(exit_value))


def _require_online_pair(
    db: Session,
    *,
    tunnel_id: int,
    iran_node_id: int,
    exit_node_id: int,
) -> Tunnel:
    tunnel = db.get(Tunnel, int(tunnel_id))
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel انتخاب‌شده پیدا نشد")
    if int(tunnel.iran_node_id) != int(iran_node_id) or int(tunnel.exit_node_id) != int(exit_node_id):
        raise HTTPException(status_code=409, detail="Tunnel با نود ایران و Exit انتخاب‌شده هم‌خوان نیست")
    if not bool(tunnel.is_active) or tunnel.status != TunnelStatus.ONLINE:
        raise HTTPException(status_code=409, detail="برای Iran Relay باید Tunnel ایران به خارج Online باشد")
    return tunnel


def _relay_options(db: Session, iran_node_id: int) -> list[dict[str, Any]]:
    tunnels = (
        db.query(Tunnel)
        .filter(Tunnel.iran_node_id == int(iran_node_id))
        .order_by(Tunnel.id.asc())
        .all()
    )
    output: list[dict[str, Any]] = []
    for tunnel in tunnels:
        exit_node = (
            db.query(Node)
            .filter(Node.id == int(tunnel.exit_node_id), Node.retired_at.is_(None))
            .first()
        )
        if not exit_node or exit_node.node_type != NodeType.EXIT:
            continue
        _, _, exit_tunnel_ip = _tunnel_addresses(int(tunnel.id))
        output.append({
            "tunnel_id": int(tunnel.id),
            "exit_node_id": int(exit_node.id),
            "exit_node_name": str(exit_node.name),
            "exit_public_ip": str(exit_node.public_ip),
            "exit_tunnel_ip": exit_tunnel_ip,
            "tunnel_status": str(getattr(tunnel.status, "value", tunnel.status)),
            "is_active": bool(tunnel.is_active),
            "active_transport": str(tunnel.active_transport or ""),
            "upstream_candidates": _candidate_rows(db, int(exit_node.id)),
        })
    return output


def _client_payload(setting: DnsEmergencyIranSetting | None) -> dict[str, Any] | None:
    if not setting or not setting.public_key or not setting.tunnel_domain:
        return None
    return {
        "engine": "dnstt",
        "mode": "iran_relay",
        "domain": setting.tunnel_domain,
        "public_key": setting.public_key,
        "local_listen": "127.0.0.1:7000",
        "resolver_examples": [
            {"label": "System / ISP", "mode": "udp", "value": "<resolver-ip>:53"},
        ],
        "command_example": (
            "dnstt-client -udp <resolver-ip>:53 "
            f"-pubkey {setting.public_key} {setting.tunnel_domain} 127.0.0.1:7000"
        ),
        "nm_dns": None,
        "nm_dns_reason": (
            "NetMod nm-dns is application-specific and encrypted; TwinPanel "
            "does not fabricate it without a verified public schema."
        ),
    }


def _payload(
    db: Session,
    iran: Node,
    setting: DnsEmergencyIranSetting | None,
) -> dict[str, Any]:
    return {
        "node_id": int(iran.id),
        "node_name": str(iran.name),
        "public_ip": str(iran.public_ip),
        "status": setting.runtime_status if setting else "not_installed",
        "exit_node_id": setting.exit_node_id if setting else None,
        "tunnel_id": setting.tunnel_id if setting else None,
        "tunnel_domain": setting.tunnel_domain if setting else None,
        "nameserver_host": setting.nameserver_host if setting else None,
        "upstream_port": setting.upstream_port if setting else None,
        "public_key": setting.public_key if setting else None,
        "last_error": setting.last_error if setting else None,
        "checked_at": setting.checked_at.isoformat() + "Z" if setting and setting.checked_at else None,
        "last_applied_at": setting.last_applied_at.isoformat() + "Z" if setting and setting.last_applied_at else None,
        "dnstt_commit": setting.dnstt_commit if setting else DNSTT_COMMIT,
        "relay_options": _relay_options(db, int(iran.id)),
        "client": _client_payload(setting),
    }


def _install_script(
    iran: Node,
    domain: str,
    exit_tunnel_ip: str,
    upstream_port: int,
) -> str:
    """Install only runtime state; the verified binary is staged by the API.

    Iran nodes deliberately do not download Go or clone GitHub here. The
    production release carries a checksum-verified DNSTT binary and transfers it
    over the already authenticated SSH connection before this script runs.
    """

    listen_addr = _listen_addr(str(iran.public_ip))
    q_commit = shlex.quote(DNSTT_COMMIT)
    q_domain = shlex.quote(domain)
    q_listen = shlex.quote(listen_addr)
    q_upstream = shlex.quote(f"{exit_tunnel_ip}:{int(upstream_port)}")
    return f"""set -Eeuo pipefail
install -d -m 0700 {STATE_DIR}
test -x {BINARY_PATH} || {{ echo "DNSTT_ARTIFACT_MISSING" >&2; exit 34; }}
printf '%s\n' {q_commit} > {STATE_DIR}/source.commit

if [ ! -s {STATE_DIR}/server.key ] || [ ! -s {STATE_DIR}/server.pub ]; then
  umask 077
  {BINARY_PATH} -gen-key -privkey-file {STATE_DIR}/server.key -pubkey-file {STATE_DIR}/server.pub
fi
chmod 0600 {STATE_DIR}/server.key
chmod 0644 {STATE_DIR}/server.pub

cat > /etc/systemd/system/{SERVICE_NAME} <<'UNIT'
[Unit]
Description=TwinPanel DNS Emergency Iran Relay
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={BINARY_PATH} -udp {listen_addr} -privkey-file {STATE_DIR}/server.key {domain} {exit_tunnel_ip}:{int(upstream_port)}
Restart=always
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
LockPersonality=true
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable {SERVICE_NAME} >/dev/null 2>&1 || true
systemctl restart {SERVICE_NAME}
sleep 1
if ! systemctl is-active --quiet {SERVICE_NAME}; then
  systemctl --no-pager --full status {SERVICE_NAME} || true
  journalctl -u {SERVICE_NAME} -n 60 --no-pager || true
  exit 41
fi

python3 - <<'PY'
import socket
s = socket.socket()
s.settimeout(3.0)
try:
    s.connect(({exit_tunnel_ip!r}, {int(upstream_port)}))
finally:
    s.close()
PY

printf 'PUBLIC_KEY='
tr -d '\r\n' < {STATE_DIR}/server.pub
printf '\n'
printf 'SERVICE=active\n'
printf 'DOMAIN=%s\n' {q_domain}
printf 'LISTEN=%s\n' {q_listen}
printf 'UPSTREAM=%s\n' {q_upstream}
printf 'DNSTT_COMMIT=%s\n' {q_commit}
"""


def _health_script(exit_tunnel_ip: str, upstream_port: int) -> str:
    return f"""set -u
service_state="$(systemctl is-active {SERVICE_NAME} 2>/dev/null || true)"
listener="no"
if ss -H -lunp 2>/dev/null | grep -F ':53 ' | grep -F 'dnstt' >/dev/null 2>&1; then
  listener="yes"
fi
upstream="no"
python3 - <<'PY' >/dev/null 2>&1 && upstream="yes" || true
import socket
s = socket.socket()
s.settimeout(3.0)
try:
    s.connect(({exit_tunnel_ip!r}, {int(upstream_port)}))
finally:
    s.close()
PY
pub=""
if [ -s {STATE_DIR}/server.pub ]; then
  pub="$(tr -d '\r\n' < {STATE_DIR}/server.pub)"
fi
printf 'SERVICE=%s\n' "$service_state"
printf 'LISTENER=%s\n' "$listener"
printf 'UPSTREAM=%s\n' "$upstream"
printf 'PUBLIC_KEY=%s\n' "$pub"
"""


def _mark_error(db: Session, iran_node_id: int, message: str) -> None:
    row = _setting(db, iran_node_id)
    if not row:
        return
    row.runtime_status = "error"
    row.last_error = str(message or "dns emergency iran relay failed")[:1800]
    row.checked_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.commit()


@router.get("/dns-emergency-iran")
def inventory(db: Session = Depends(get_db)):
    nodes = (
        db.query(Node)
        .filter(Node.node_type == NodeType.IRAN, Node.retired_at.is_(None))
        .order_by(Node.id.asc())
        .all()
    )
    return {
        "ok": True,
        "engine": "dnstt",
        "mode": "iran_relay",
        "source": {
            "repository": DNSTT_REPOSITORY,
            "commit": DNSTT_COMMIT,
            "go_version": GO_VERSION,
        },
        "nodes": [_payload(db, node, _setting(db, int(node.id))) for node in nodes],
    }


@router.post("/dns-emergency-iran/{iran_node_id}/install")
async def install(
    iran_node_id: int,
    payload: DnsEmergencyIranInstallIn,
    db: Session = Depends(get_db),
):
    iran = _node(db, iran_node_id, NodeType.IRAN)
    exit_node = _node(db, payload.exit_node_id, NodeType.EXIT)
    tunnel = _require_online_pair(
        db,
        tunnel_id=payload.tunnel_id,
        iran_node_id=iran.id,
        exit_node_id=exit_node.id,
    )
    domain = _normalize_domain(payload.tunnel_domain, field_name="Tunnel Domain")
    nameserver = _normalize_domain(payload.nameserver_host, field_name="Nameserver") if payload.nameserver_host else None
    upstream_port = int(payload.upstream_port)

    candidates = _candidate_rows(db, int(exit_node.id))
    if not candidates:
        raise HTTPException(status_code=409, detail="هیچ سرویس TCP شناخته‌شده‌ای روی Exit انتخاب‌شده آماده نیست")
    if upstream_port not in {int(item["port"]) for item in candidates}:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "پورت مقصد باید متعلق به یک سرویس TCP شناخته‌شده روی Exit انتخاب‌شده باشد",
                "allowed_ports": [int(item["port"]) for item in candidates],
            },
        )

    _, _, exit_tunnel_ip = _tunnel_addresses(int(tunnel.id))
    row = _setting(db, int(iran.id))
    if not row:
        row = DnsEmergencyIranSetting(iran_node_id=int(iran.id))
        db.add(row)
    row.exit_node_id = int(exit_node.id)
    row.tunnel_id = int(tunnel.id)
    row.tunnel_domain = domain
    row.nameserver_host = nameserver
    row.upstream_port = upstream_port
    row.dnstt_commit = DNSTT_COMMIT
    row.runtime_status = "installing"
    row.last_error = None
    row.updated_at = datetime.utcnow()
    db.commit()

    artifact_info: dict[str, str] = {}
    try:
        conn = await _connect(iran, db)
        try:
            artifact_info = await stage_dnstt_binary(conn, BINARY_PATH)
            result = await _run_script(
                conn,
                _install_script(iran, domain, exit_tunnel_ip, upstream_port),
            )
        finally:
            conn.close()
            await conn.wait_closed()
    except Exception as exc:
        _mark_error(db, int(iran.id), str(exc))
        raise HTTPException(
            status_code=502,
            detail={"message": "اتصال/نصب DNS Emergency Iran Relay ناموفق بود", "error": str(exc)[:1800]},
        ) from exc

    parsed = _parse_lines(result.stdout)
    if int(getattr(result, "exit_status", 1) or 0) != 0:
        message = str(result.stderr or result.stdout or "dnstt iran relay install failed")
        _mark_error(db, int(iran.id), message)
        raise HTTPException(
            status_code=502,
            detail={"message": "نصب DNS Emergency روی نود ایران ناموفق بود", "error": message[-1800:]},
        )

    public_key = parsed.get("PUBLIC_KEY", "")
    if not public_key:
        _mark_error(db, int(iran.id), "dnstt public key missing")
        raise HTTPException(status_code=502, detail="کلید عمومی DNSTT از نود ایران دریافت نشد")

    row = _setting(db, int(iran.id))
    if not row:
        raise HTTPException(status_code=500, detail="وضعیت Iran Relay ذخیره نشد")
    row.public_key = public_key
    row.runtime_status = "online"
    row.last_error = None
    row.checked_at = datetime.utcnow()
    row.last_applied_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.commit()

    record_type = "AAAA" if ipaddress.ip_address(str(iran.public_ip)).version == 6 else "A"
    return {
        "ok": True,
        **_payload(db, iran, row),
        "runtime": {
            "exit_tunnel_ip": exit_tunnel_ip,
            "active_transport": str(tunnel.active_transport or ""),
            "dnstt_artifact": artifact_info,
        },
        "dns_instructions": {
            "tunnel_domain": domain,
            "nameserver_host": nameserver,
            "iran_ip": iran.public_ip,
            "records": ([
                {"type": record_type, "name": nameserver, "value": iran.public_ip},
                {"type": "NS", "name": domain, "value": nameserver},
            ] if nameserver else []),
        },
    }


@router.post("/dns-emergency-iran/{iran_node_id}/health")
async def health(iran_node_id: int, db: Session = Depends(get_db)):
    iran = _node(db, iran_node_id, NodeType.IRAN)
    row = _setting(db, int(iran.id))
    if not row or not row.tunnel_id or not row.exit_node_id or not row.upstream_port:
        raise HTTPException(status_code=409, detail="DNS Emergency Iran Relay روی این نود نصب نشده است")

    tunnel = _require_online_pair(
        db,
        tunnel_id=int(row.tunnel_id),
        iran_node_id=int(iran.id),
        exit_node_id=int(row.exit_node_id),
    )
    _, _, exit_tunnel_ip = _tunnel_addresses(int(tunnel.id))

    try:
        conn = await _connect(iran, db)
        try:
            result = await _run_script(conn, _health_script(exit_tunnel_ip, int(row.upstream_port)))
        finally:
            conn.close()
            await conn.wait_closed()
    except Exception as exc:
        _mark_error(db, int(iran.id), str(exc))
        raise HTTPException(
            status_code=502,
            detail={"message": "Health Check Iran Relay ناموفق بود", "error": str(exc)[:1800]},
        ) from exc

    parsed = _parse_lines(result.stdout)
    ok = (
        int(getattr(result, "exit_status", 1) or 0) == 0
        and parsed.get("SERVICE") == "active"
        and parsed.get("LISTENER") == "yes"
        and parsed.get("UPSTREAM") == "yes"
    )
    row.runtime_status = "online" if ok else "error"
    row.public_key = parsed.get("PUBLIC_KEY") or row.public_key
    row.last_error = None if ok else (
        f"service={parsed.get('SERVICE','unknown')}; listener={parsed.get('LISTENER','unknown')}; upstream={parsed.get('UPSTREAM','unknown')}"
    )
    row.checked_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.commit()
    return {
        "ok": ok,
        **_payload(db, iran, row),
        "runtime": {
            **parsed,
            "exit_tunnel_ip": exit_tunnel_ip,
            "active_transport": str(tunnel.active_transport or ""),
        },
    }


@router.delete("/dns-emergency-iran/{iran_node_id}")
async def remove(iran_node_id: int, db: Session = Depends(get_db)):
    iran = _node(db, iran_node_id, NodeType.IRAN)
    row = _setting(db, int(iran.id))
    if not row:
        return {"ok": True, "node_id": iran.id, "status": "not_installed"}

    script = f"""set -u
systemctl disable --now {SERVICE_NAME} >/dev/null 2>&1 || true
rm -f /etc/systemd/system/{SERVICE_NAME}
systemctl daemon-reload
printf 'REMOVED=yes\n'
"""
    try:
        conn = await _connect(iran, db)
        try:
            result = await _run_script(conn, script)
        finally:
            conn.close()
            await conn.wait_closed()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "حذف DNS Emergency Iran Relay ناموفق بود", "error": str(exc)[:1800]},
        ) from exc

    if int(getattr(result, "exit_status", 1) or 0) != 0:
        raise HTTPException(
            status_code=502,
            detail={"message": "حذف DNS Emergency Iran Relay ناموفق بود", "error": str(result.stderr or result.stdout or "")[-1800:]},
        )

    row.runtime_status = "not_installed"
    row.last_error = None
    row.checked_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, **_payload(db, iran, row)}
