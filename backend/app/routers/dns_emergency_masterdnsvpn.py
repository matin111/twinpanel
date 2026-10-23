from __future__ import annotations

import base64
import ipaddress
import re
import shlex
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..masterdnsvpn_artifact import stage_masterdnsvpn_binary
from ..masterdnsvpn_models import MasterDnsVpnSetting
from ..models import Node, NodeType
from .dns_emergency import _connect, _listen_addr, _normalize_domain, _parse_lines, _run_script


router = APIRouter(
    prefix="/v1/settings/vpn",
    tags=["dns-emergency-masterdnsvpn"],
    dependencies=[Depends(require_admin)],
)

MASTERDNSVPN_REPOSITORY = "https://github.com/masterking32/MasterDnsVPN.git"
MASTERDNSVPN_COMMIT = "acbf1c61f90786f41b975d2e2f616afbce292b29"
MASTERDNSVPN_GO_VERSION = "1.25.0"
SERVICE_NAME = "twinpanel-masterdnsvpn.service"
BINARY_PATH = "/usr/local/bin/twinpanel-masterdnsvpn-server"
STATE_DIR = "/etc/twinpanel/masterdnsvpn"
CONFIG_PATH = f"{STATE_DIR}/server_config.toml"
KEY_PATH = f"{STATE_DIR}/encrypt_key.txt"
ALLOWED_ENCRYPTION_METHODS = {2, 3, 4, 5}
HOST_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
    re.IGNORECASE,
)


class MasterDnsVpnInstallIn(BaseModel):
    tunnel_domain: str = Field(min_length=4, max_length=253)
    nameserver_host: str | None = Field(default=None, max_length=253)
    protocol_type: str = Field(default="SOCKS5", max_length=16)
    forward_ip: str | None = Field(default=None, max_length=253)
    forward_port: int | None = Field(default=None, ge=1, le=65535)
    data_encryption_method: int = Field(default=2, ge=2, le=5)


def _exit_node(db: Session, node_id: int) -> Node:
    node = (
        db.query(Node)
        .filter(Node.id == int(node_id), Node.retired_at.is_(None))
        .first()
    )
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    if node.node_type != NodeType.EXIT:
        raise HTTPException(
            status_code=400,
            detail="MasterDnsVPN Direct Exit فقط روی Exit Node نصب می‌شود",
        )
    try:
        ipaddress.ip_address(str(node.public_ip))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Public IP نود معتبر نیست") from exc
    return node


def _setting(db: Session, node_id: int) -> MasterDnsVpnSetting | None:
    return (
        db.query(MasterDnsVpnSetting)
        .filter(MasterDnsVpnSetting.node_id == int(node_id))
        .first()
    )


def _protocol_type(value: str) -> str:
    mode = str(value or "").strip().upper()
    if mode not in {"SOCKS5", "TCP"}:
        raise HTTPException(status_code=422, detail="Protocol Type باید SOCKS5 یا TCP باشد")
    return mode


def _forward_host(value: str | None) -> str | None:
    raw = str(value or "").strip().lower().rstrip(".")
    if not raw:
        return None
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        if not HOST_RE.fullmatch(raw):
            raise HTTPException(status_code=422, detail="Forward Host معتبر نیست")
        return raw


def _payload(node: Node, setting: MasterDnsVpnSetting | None) -> dict[str, Any]:
    return {
        "node_id": int(node.id),
        "node_name": str(node.name),
        "public_ip": str(node.public_ip),
        "status": setting.runtime_status if setting else "not_installed",
        "tunnel_domain": setting.tunnel_domain if setting else None,
        "nameserver_host": setting.nameserver_host if setting else None,
        "protocol_type": setting.protocol_type if setting else "SOCKS5",
        "forward_ip": setting.forward_ip if setting else None,
        "forward_port": setting.forward_port if setting else None,
        "data_encryption_method": int(setting.data_encryption_method) if setting else 2,
        "source_commit": (
            setting.source_commit
            if setting and setting.source_commit
            else MASTERDNSVPN_COMMIT
        ),
        "last_error": setting.last_error if setting else None,
        "checked_at": (
            setting.checked_at.isoformat() + "Z"
            if setting and setting.checked_at
            else None
        ),
        "last_applied_at": (
            setting.last_applied_at.isoformat() + "Z"
            if setting and setting.last_applied_at
            else None
        ),
        "client_config_available": bool(
            setting
            and setting.runtime_status != "not_installed"
            and setting.tunnel_domain
        ),
    }


def _server_config(
    *,
    public_ip: str,
    domain: str,
    protocol_type: str,
    forward_ip: str | None,
    forward_port: int | None,
    encryption_method: int,
) -> str:
    return "\n".join(
        [
            f'DOMAIN = ["{domain}"]',
            f'PROTOCOL_TYPE = "{protocol_type}"',
            f'UDP_HOST = "{public_ip}"',
            "UDP_PORT = 53",
            'DNS_UPSTREAM_SERVERS = ["1.1.1.1:53", "8.8.8.8:53"]',
            "DNS_UPSTREAM_TIMEOUT = 4.0",
            "SOCKS_CONNECT_TIMEOUT = 60.0",
            "USE_EXTERNAL_SOCKS5 = false",
            f'FORWARD_IP = "{forward_ip or ""}"',
            f"FORWARD_PORT = {int(forward_port or 0)}",
            f"DATA_ENCRYPTION_METHOD = {int(encryption_method)}",
            f'ENCRYPTION_KEY_FILE = "{KEY_PATH}"',
            'LOG_LEVEL = "ERROR"',
            'CONFIG_VERSION = "12"',
            "",
        ]
    )


def _install_script(
    *,
    node: Node,
    domain: str,
    protocol_type: str,
    forward_ip: str | None,
    forward_port: int | None,
    encryption_method: int,
) -> str:
    public_ip = str(ipaddress.ip_address(str(node.public_ip)))
    config = _server_config(
        public_ip=public_ip,
        domain=domain,
        protocol_type=protocol_type,
        forward_ip=forward_ip,
        forward_port=forward_port,
        encryption_method=encryption_method,
    )
    encoded_config = base64.b64encode(config.encode("utf-8")).decode("ascii")
    q_public_ip = shlex.quote(public_ip)
    q_commit = shlex.quote(MASTERDNSVPN_COMMIT)
    q_config = shlex.quote(encoded_config)
    tcp_probe = ""
    if protocol_type == "TCP" and forward_ip and forward_port:
        tcp_probe = f"""
python3 - <<'PY'
import socket
s = socket.create_connection(({forward_ip!r}, {int(forward_port)}), timeout=4.0)
s.close()
PY
"""

    return f"""set -Eeuo pipefail
install -d -m 0700 {STATE_DIR}
test -x {BINARY_PATH} || {{ echo "MASTERDNSVPN_ARTIFACT_MISSING" >&2; exit 34; }}
printf '%s' {q_config} | base64 -d > {CONFIG_PATH}
chmod 0600 {CONFIG_PATH}
printf '%s\n' {q_commit} > {STATE_DIR}/source.commit
chmod 0600 {STATE_DIR}/source.commit

own_pid="$(systemctl show {SERVICE_NAME} -p MainPID --value 2>/dev/null || true)"
PUBLIC_IP={q_public_ip} OWN_PID="$own_pid" python3 - <<'PY'
import ipaddress
import os
import subprocess
import sys

public_ip = str(ipaddress.ip_address(os.environ["PUBLIC_IP"]))
own_pid = os.environ.get("OWN_PID", "").strip()
output = subprocess.run(
    ["ss", "-H", "-lunp"],
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    check=False,
).stdout

def host_from_endpoint(token: str):
    token = token.strip()
    if not token.endswith(":53"):
        return None
    host = token[:-3]
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host.split("%", 1)[0]

conflicts = []
for line in output.splitlines():
    if own_pid and f"pid={{own_pid}}," in line:
        continue
    endpoints = [host_from_endpoint(part) for part in line.split()]
    hosts = {{value for value in endpoints if value is not None}}
    if public_ip in hosts or "0.0.0.0" in hosts or "::" in hosts or "*" in hosts:
        conflicts.append(line)

if conflicts:
    print("UDP53_CONFLICT", file=sys.stderr)
    for line in conflicts[:8]:
        print(line, file=sys.stderr)
    raise SystemExit(52)
PY

if [ ! -s {KEY_PATH} ]; then
  umask 077
  {BINARY_PATH} -config {CONFIG_PATH} -genkey -nowait >/dev/null 2>&1
fi
test -s {KEY_PATH}
chmod 0600 {KEY_PATH}
{tcp_probe}
cat > /etc/systemd/system/{SERVICE_NAME} <<'UNIT'
[Unit]
Description=TwinPanel MasterDnsVPN Direct Exit
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={BINARY_PATH} -config {CONFIG_PATH} -nowait
Restart=always
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
LockPersonality=true
MemoryDenyWriteExecute=true
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
  journalctl -u {SERVICE_NAME} -n 40 --no-pager || true
  exit 41
fi

main_pid="$(systemctl show {SERVICE_NAME} -p MainPID --value)"
if ! ss -H -lunp 2>/dev/null | grep -F "pid=$main_pid," | grep -F ':53 ' >/dev/null 2>&1; then
  echo "MASTERDNSVPN_UDP53_LISTENER_MISSING" >&2
  exit 42
fi

printf 'SERVICE=active\n'
printf 'LISTENER=yes\n'
printf 'DOMAIN=%s\n' {shlex.quote(domain)}
printf 'MODE=%s\n' {shlex.quote(protocol_type)}
printf 'LISTEN=%s\n' {shlex.quote(_listen_addr(public_ip))}
printf 'SOURCE_COMMIT=%s\n' {q_commit}
"""


def _health_script(
    *,
    protocol_type: str,
    forward_ip: str | None,
    forward_port: int | None,
) -> str:
    tcp_check = "n/a"
    tcp_probe = ""
    if protocol_type == "TCP" and forward_ip and forward_port:
        tcp_check = "no"
        tcp_probe = f"""
python3 - <<'PY' >/dev/null 2>&1 && upstream="yes" || true
import socket
s = socket.create_connection(({forward_ip!r}, {int(forward_port)}), timeout=4.0)
s.close()
PY
"""
    return f"""set -u
service_state="$(systemctl is-active {SERVICE_NAME} 2>/dev/null || true)"
main_pid="$(systemctl show {SERVICE_NAME} -p MainPID --value 2>/dev/null || true)"
listener="no"
if [ -n "$main_pid" ] && [ "$main_pid" != "0" ]; then
  if ss -H -lunp 2>/dev/null | grep -F "pid=$main_pid," | grep -F ':53 ' >/dev/null 2>&1; then
    listener="yes"
  fi
fi
source_ok="no"
if [ -f {STATE_DIR}/source.commit ] && [ "$(tr -d '\r\n' < {STATE_DIR}/source.commit)" = {shlex.quote(MASTERDNSVPN_COMMIT)} ]; then
  source_ok="yes"
fi
key_ok="no"
if [ -s {KEY_PATH} ]; then
  key_ok="yes"
fi
upstream={shlex.quote(tcp_check)}
{tcp_probe}
printf 'SERVICE=%s\n' "$service_state"
printf 'LISTENER=%s\n' "$listener"
printf 'SOURCE=%s\n' "$source_ok"
printf 'KEY=%s\n' "$key_ok"
printf 'UPSTREAM=%s\n' "$upstream"
"""


def _mark_error(db: Session, node_id: int, message: str) -> None:
    row = _setting(db, node_id)
    if not row:
        return
    row.runtime_status = "error"
    row.last_error = str(message or "MasterDnsVPN failed")[:1800]
    row.checked_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.commit()


def _dns_instructions(node: Node, domain: str, nameserver: str | None) -> dict[str, Any]:
    record_type = "AAAA" if ipaddress.ip_address(str(node.public_ip)).version == 6 else "A"
    records = []
    if nameserver:
        records = [
            {"type": record_type, "name": nameserver, "value": str(node.public_ip)},
            {"type": "NS", "name": domain, "value": nameserver},
        ]
    return {
        "tunnel_domain": domain,
        "nameserver_host": nameserver,
        "exit_ip": str(node.public_ip),
        "records": records,
    }


def _client_config_text(setting: MasterDnsVpnSetting, key: str) -> str:
    return "\n".join(
        [
            f'DOMAINS = ["{setting.tunnel_domain}"]',
            f"DATA_ENCRYPTION_METHOD = {int(setting.data_encryption_method)}",
            f'ENCRYPTION_KEY = "{key}"',
            f'PROTOCOL_TYPE = "{setting.protocol_type}"',
            'LISTEN_IP = "127.0.0.1"',
            "LISTEN_PORT = 18000",
            "SOCKS5_AUTH = false",
            "LOCAL_DNS_ENABLED = false",
            'LOG_LEVEL = "INFO"',
            "",
        ]
    )


@router.get("/dns-emergency-masterdnsvpn")
def inventory(db: Session = Depends(get_db)):
    nodes = (
        db.query(Node)
        .filter(Node.node_type == NodeType.EXIT, Node.retired_at.is_(None))
        .order_by(Node.id.asc())
        .all()
    )
    return {
        "ok": True,
        "engine": "masterdnsvpn",
        "mode": "direct_exit",
        "source": {
            "repository": MASTERDNSVPN_REPOSITORY,
            "commit": MASTERDNSVPN_COMMIT,
            "go_version": MASTERDNSVPN_GO_VERSION,
        },
        "security": {
            "udp53_conflict_policy": "fail_closed",
            "secret_in_inventory": False,
            "supported_encryption_methods": [2, 3, 4, 5],
        },
        "nodes": [_payload(node, _setting(db, int(node.id))) for node in nodes],
    }


@router.post("/dns-emergency-masterdnsvpn/{node_id}/install")
async def install(
    node_id: int,
    payload: MasterDnsVpnInstallIn,
    db: Session = Depends(get_db),
):
    node = _exit_node(db, node_id)
    domain = _normalize_domain(payload.tunnel_domain, field_name="Tunnel Domain")
    nameserver = (
        _normalize_domain(payload.nameserver_host, field_name="Nameserver")
        if payload.nameserver_host
        else None
    )
    mode = _protocol_type(payload.protocol_type)
    encryption_method = int(payload.data_encryption_method)
    if encryption_method not in ALLOWED_ENCRYPTION_METHODS:
        raise HTTPException(
            status_code=422,
            detail="Encryption Method باید یکی از ChaCha20/AES-GCM باشد",
        )

    forward_ip = _forward_host(payload.forward_ip)
    forward_port = int(payload.forward_port) if payload.forward_port else None
    if mode == "TCP" and (not forward_ip or not forward_port):
        raise HTTPException(
            status_code=422,
            detail="در حالت TCP، Forward Host و Forward Port الزامی است",
        )
    if mode == "SOCKS5":
        forward_ip = None
        forward_port = None

    row = _setting(db, node.id)
    if not row:
        row = MasterDnsVpnSetting(node_id=node.id)
        db.add(row)
    row.tunnel_domain = domain
    row.nameserver_host = nameserver
    row.protocol_type = mode
    row.forward_ip = forward_ip
    row.forward_port = forward_port
    row.data_encryption_method = encryption_method
    row.source_commit = MASTERDNSVPN_COMMIT
    row.runtime_status = "installing"
    row.last_error = None
    row.updated_at = datetime.utcnow()
    db.commit()

    artifact_meta: dict[str, str] = {}
    try:
        conn = await _connect(node, db)
        try:
            artifact_meta = await stage_masterdnsvpn_binary(conn, BINARY_PATH)
            result = await _run_script(
                conn,
                _install_script(
                    node=node,
                    domain=domain,
                    protocol_type=mode,
                    forward_ip=forward_ip,
                    forward_port=forward_port,
                    encryption_method=encryption_method,
                ),
            )
        finally:
            conn.close()
            await conn.wait_closed()
    except Exception as exc:
        _mark_error(db, node.id, str(exc))
        raise HTTPException(
            status_code=502,
            detail={
                "message": "اتصال/نصب MasterDnsVPN روی Exit ناموفق بود",
                "error": str(exc)[:1800],
            },
        ) from exc

    if int(getattr(result, "exit_status", 1) or 0) != 0:
        message = str(result.stderr or result.stdout or "MasterDnsVPN install failed")
        _mark_error(db, node.id, message)
        raise HTTPException(
            status_code=502,
            detail={
                "message": "نصب MasterDnsVPN روی Exit ناموفق بود",
                "error": message[-1800:],
            },
        )

    parsed = _parse_lines(result.stdout)
    ok = (
        parsed.get("SERVICE") == "active"
        and parsed.get("LISTENER") == "yes"
        and parsed.get("SOURCE_COMMIT") == MASTERDNSVPN_COMMIT
    )
    if not ok:
        message = (
            f"service={parsed.get('SERVICE','unknown')}; "
            f"listener={parsed.get('LISTENER','unknown')}; "
            f"source={parsed.get('SOURCE_COMMIT','unknown')}"
        )
        _mark_error(db, node.id, message)
        raise HTTPException(
            status_code=502,
            detail={"message": "Health اولیه MasterDnsVPN ناموفق بود", "error": message},
        )

    row = _setting(db, node.id)
    if not row:
        raise HTTPException(status_code=500, detail="وضعیت MasterDnsVPN ذخیره نشد")
    row.runtime_status = "online"
    row.last_error = None
    row.checked_at = datetime.utcnow()
    row.last_applied_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.commit()

    return {
        "ok": True,
        **_payload(node, row),
        "artifact": artifact_meta,
        "dns_instructions": _dns_instructions(node, domain, nameserver),
    }


@router.post("/dns-emergency-masterdnsvpn/{node_id}/health")
async def health(node_id: int, db: Session = Depends(get_db)):
    node = _exit_node(db, node_id)
    row = _setting(db, node.id)
    if not row or not row.tunnel_domain:
        raise HTTPException(status_code=409, detail="MasterDnsVPN روی این Exit نصب نشده است")

    try:
        conn = await _connect(node, db)
        try:
            result = await _run_script(
                conn,
                _health_script(
                    protocol_type=str(row.protocol_type),
                    forward_ip=row.forward_ip,
                    forward_port=row.forward_port,
                ),
            )
        finally:
            conn.close()
            await conn.wait_closed()
    except Exception as exc:
        _mark_error(db, node.id, str(exc))
        raise HTTPException(
            status_code=502,
            detail={"message": "Health Check ناموفق بود", "error": str(exc)[:1800]},
        ) from exc

    parsed = _parse_lines(result.stdout)
    upstream_ok = parsed.get("UPSTREAM") == "yes" if str(row.protocol_type).upper() == "TCP" else True
    ok = (
        int(getattr(result, "exit_status", 1) or 0) == 0
        and parsed.get("SERVICE") == "active"
        and parsed.get("LISTENER") == "yes"
        and parsed.get("SOURCE") == "yes"
        and parsed.get("KEY") == "yes"
        and upstream_ok
    )

    row.runtime_status = "online" if ok else "error"
    row.last_error = None if ok else (
        f"service={parsed.get('SERVICE','unknown')}; "
        f"listener={parsed.get('LISTENER','unknown')}; "
        f"source={parsed.get('SOURCE','unknown')}; "
        f"key={parsed.get('KEY','unknown')}; "
        f"upstream={parsed.get('UPSTREAM','unknown')}"
    )
    row.checked_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.commit()

    return {"ok": ok, **_payload(node, row), "runtime": parsed}


@router.get("/dns-emergency-masterdnsvpn/{node_id}/client-config")
async def client_config(node_id: int, db: Session = Depends(get_db)):
    node = _exit_node(db, node_id)
    row = _setting(db, node.id)
    if not row or not row.tunnel_domain or row.runtime_status == "not_installed":
        raise HTTPException(status_code=409, detail="MasterDnsVPN روی این Exit نصب نشده است")

    script = f"""set -Eeuo pipefail
test -s {KEY_PATH}
key="$(tr -d '\r\n' < {KEY_PATH})"
test -n "$key"
printf 'KEY=%s\n' "$key"
"""
    try:
        conn = await _connect(node, db)
        try:
            result = await _run_script(conn, script)
        finally:
            conn.close()
            await conn.wait_closed()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "دریافت Client Config ناموفق بود", "error": str(exc)[:1800]},
        ) from exc

    if int(getattr(result, "exit_status", 1) or 0) != 0:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "کلید MasterDnsVPN از Exit دریافت نشد",
                "error": str(result.stderr or result.stdout or "")[-1200:],
            },
        )

    key = _parse_lines(result.stdout).get("KEY", "")
    if not key or len(key) > 512 or any(ch.isspace() for ch in key):
        raise HTTPException(status_code=502, detail="کلید MasterDnsVPN معتبر نیست")

    resolvers = "\n".join(
        [
            "# One resolver per line. Prefer resolvers reachable on the target network.",
            "1.1.1.1:53",
            "8.8.8.8:53",
            "",
        ]
    )
    return {
        "ok": True,
        "node_id": int(node.id),
        "engine": "masterdnsvpn",
        "mode": "direct_exit",
        "secret": True,
        "domain": str(row.tunnel_domain),
        "protocol_type": str(row.protocol_type),
        "encryption_method": int(row.data_encryption_method),
        "encryption_key": key,
        "client_config_toml": _client_config_text(row, key),
        "client_resolvers_txt": resolvers,
        "command_example": (
            "masterdnsvpn-client -config client_config.toml "
            "-resolvers client_resolvers.txt"
        ),
        "dns_instructions": _dns_instructions(
            node,
            str(row.tunnel_domain),
            row.nameserver_host,
        ),
    }


@router.delete("/dns-emergency-masterdnsvpn/{node_id}")
async def remove(node_id: int, db: Session = Depends(get_db)):
    node = _exit_node(db, node_id)
    row = _setting(db, node.id)
    if not row:
        return {"ok": True, "node_id": int(node.id), "status": "not_installed"}

    script = f"""set -u
systemctl disable --now {SERVICE_NAME} >/dev/null 2>&1 || true
rm -f /etc/systemd/system/{SERVICE_NAME}
systemctl daemon-reload
printf 'REMOVED=yes\n'
"""
    try:
        conn = await _connect(node, db)
        try:
            result = await _run_script(conn, script)
        finally:
            conn.close()
            await conn.wait_closed()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "حذف MasterDnsVPN ناموفق بود", "error": str(exc)[:1800]},
        ) from exc

    if int(getattr(result, "exit_status", 1) or 0) != 0:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "حذف MasterDnsVPN ناموفق بود",
                "error": str(result.stderr or result.stdout or "")[-1800:],
            },
        )

    row.runtime_status = "not_installed"
    row.last_error = None
    row.checked_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, **_payload(node, row)}
