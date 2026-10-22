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
from ..dns_emergency_models import DnsEmergencySetting
from ..models import Node, NodeProtocolConfig, NodeType


router = APIRouter(
    prefix="/v1/settings/vpn",
    tags=["dns-emergency"],
    dependencies=[Depends(require_admin)],
)

DNSTT_REPOSITORY = "https://github.com/OutlineFoundation/dnstt.git"
DNSTT_COMMIT = "e1af37b31a778cab0166788fe2549169f345d742"
GO_VERSION = "1.23.12"
GO_SHA256 = {
    "amd64": "d3847fef834e9db11bf64e3fb34db9c04db14e068eeb064f49af747010454f90",
    "arm64": "52ce172f96e21da53b1ae9079808560d49b02ac86cecfa457217597f9bc28ab3",
}
SERVICE_NAME = "twinpanel-dnstt.service"
BINARY_PATH = "/usr/local/bin/twinpanel-dnstt-server"
STATE_DIR = "/etc/twinpanel/dnstt"
GO_ROOT = f"/opt/twinpanel/toolchains/go{GO_VERSION}"
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}\.?$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.?$",
    re.IGNORECASE,
)


class DnsEmergencyInstallIn(BaseModel):
    tunnel_domain: str = Field(min_length=4, max_length=253)
    nameserver_host: str | None = Field(default=None, max_length=253)
    upstream_port: int = Field(ge=1, le=65535)


def _normalize_domain(value: str, *, field_name: str) -> str:
    domain = str(value or "").strip().lower().rstrip(".")
    if not DOMAIN_RE.fullmatch(domain):
        raise HTTPException(status_code=422, detail=f"{field_name} معتبر نیست")
    return domain


def _exit_node(db: Session, node_id: int) -> Node:
    node = (
        db.query(Node)
        .filter(Node.id == int(node_id), Node.retired_at.is_(None))
        .first()
    )
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    if node.node_type != NodeType.EXIT:
        raise HTTPException(status_code=400, detail="DNS Emergency فقط روی Exit Node نصب می‌شود")
    try:
        ipaddress.ip_address(str(node.public_ip))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Public IP نود معتبر نیست") from exc
    return node


def _setting(db: Session, node_id: int) -> DnsEmergencySetting | None:
    return (
        db.query(DnsEmergencySetting)
        .filter(DnsEmergencySetting.node_id == int(node_id))
        .first()
    )


def _tcp_capable(transport: str) -> bool:
    value = str(transport or "").strip().lower()
    if not value:
        return False
    if any(token in value for token in ("tcp", "tls", "http", "websocket", "reality", "grpc", "xhttp")):
        return True
    return "udp" not in value and "quic" not in value


def _candidate_rows(db: Session, node_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == int(node_id),
            NodeProtocolConfig.port.isnot(None),
        )
        .order_by(NodeProtocolConfig.protocol.asc())
        .all()
    )
    result: list[dict[str, Any]] = []
    seen_ports: set[int] = set()
    for row in rows:
        port = int(row.port or 0)
        if not 1 <= port <= 65535 or port in seen_ports or not _tcp_capable(row.transport):
            continue
        seen_ports.add(port)
        result.append({
            "protocol": str(row.protocol),
            "port": port,
            "transport": str(row.transport or ""),
            "service": str(row.service_name or ""),
            "status": str(row.status or ""),
            "recommended": str(row.status or "").lower() == "online",
        })
    return result


def _client_payload(setting: DnsEmergencySetting | None) -> dict[str, Any] | None:
    if not setting or not setting.public_key or not setting.tunnel_domain:
        return None
    domain = setting.tunnel_domain
    pubkey = setting.public_key
    return {
        "engine": "dnstt",
        "domain": domain,
        "public_key": pubkey,
        "local_listen": "127.0.0.1:7000",
        "resolver_examples": [
            {"label": "Cloudflare", "mode": "udp", "value": "1.1.1.1:53"},
            {"label": "Google", "mode": "udp", "value": "8.8.8.8:53"},
            {"label": "System / ISP", "mode": "udp", "value": "<resolver-ip>:53"},
        ],
        "command_example": (
            "dnstt-client -udp 1.1.1.1:53 "
            f"-pubkey {pubkey} {domain} 127.0.0.1:7000"
        ),
        "nm_dns": None,
        "nm_dns_reason": (
            "NetMod nm-dns is an opaque application-specific encrypted format; "
            "TwinPanel does not fabricate it without a verified public schema."
        ),
    }


def _setting_payload(node: Node, setting: DnsEmergencySetting | None, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "node_id": node.id,
        "node_name": node.name,
        "public_ip": node.public_ip,
        "status": setting.runtime_status if setting else "not_installed",
        "tunnel_domain": setting.tunnel_domain if setting else None,
        "nameserver_host": setting.nameserver_host if setting else None,
        "upstream_port": setting.upstream_port if setting else None,
        "public_key": setting.public_key if setting else None,
        "last_error": setting.last_error if setting else None,
        "checked_at": setting.checked_at.isoformat() + "Z" if setting and setting.checked_at else None,
        "last_applied_at": setting.last_applied_at.isoformat() + "Z" if setting and setting.last_applied_at else None,
        "dnstt_commit": setting.dnstt_commit if setting else DNSTT_COMMIT,
        "upstream_candidates": candidates,
        "client": _client_payload(setting),
    }


async def _connect(node: Node, db: Session):
    from .provision import ssh_connect_saved
    return await ssh_connect_saved(node, db)


async def _run_script(conn: Any, script: str):
    encoded = base64.b64encode(script.encode("utf-8")).decode("ascii")
    command = f"printf %s {shlex.quote(encoded)} | base64 -d | bash"
    return await conn.run(command, check=False)


def _listen_addr(public_ip: str) -> str:
    parsed = ipaddress.ip_address(public_ip)
    return f"[{parsed.compressed}]:53" if parsed.version == 6 else f"{parsed.compressed}:53"


def _install_script(node: Node, domain: str, upstream_port: int) -> str:
    listen_addr = _listen_addr(str(node.public_ip))
    q_repo = shlex.quote(DNSTT_REPOSITORY)
    q_commit = shlex.quote(DNSTT_COMMIT)
    q_domain = shlex.quote(domain)
    q_listen = shlex.quote(listen_addr)
    q_upstream = shlex.quote(f"127.0.0.1:{int(upstream_port)}")
    go_amd64_sha = GO_SHA256["amd64"]
    go_arm64_sha = GO_SHA256["arm64"]
    return f"""set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
install -d -m 0700 {STATE_DIR}

if ! command -v git >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1 || ! command -v tar >/dev/null 2>&1; then
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "UNSUPPORTED_PACKAGE_MANAGER" >&2
    exit 31
  fi
  apt-get update -y
  apt-get install -y --no-install-recommends ca-certificates curl git tar
fi

GO_ROOT={shlex.quote(GO_ROOT)}
GO_BIN="$GO_ROOT/bin/go"
if [ ! -x "$GO_BIN" ] || [ "$("$GO_BIN" version 2>/dev/null | awk '{{print $3}}')" != "go{GO_VERSION}" ]; then
  machine="$(uname -m)"
  case "$machine" in
    x86_64|amd64)
      go_arch="amd64"
      go_sha="{go_amd64_sha}"
      ;;
    aarch64|arm64)
      go_arch="arm64"
      go_sha="{go_arm64_sha}"
      ;;
    *)
      echo "UNSUPPORTED_GO_ARCH=$machine" >&2
      exit 32
      ;;
  esac
  go_work="$(mktemp -d)"
  cleanup_go() {{ rm -rf "$go_work"; }}
  trap cleanup_go EXIT
  go_tar="$go_work/go.tgz"
  curl -fsSL --retry 3 --connect-timeout 10 \
    "https://go.dev/dl/go{GO_VERSION}.linux-${{go_arch}}.tar.gz" \
    -o "$go_tar"
  printf '%s  %s\n' "$go_sha" "$go_tar" | sha256sum -c -
  mkdir -p "$go_work/root"
  tar -C "$go_work/root" -xzf "$go_tar"
  test -x "$go_work/root/go/bin/go"
  install -d -m 0755 "$(dirname "$GO_ROOT")"
  rm -rf "$GO_ROOT.next"
  mv "$go_work/root/go" "$GO_ROOT.next"
  rm -rf "$GO_ROOT"
  mv "$GO_ROOT.next" "$GO_ROOT"
  trap - EXIT
  cleanup_go
fi

if [ "$("$GO_BIN" version | awk '{{print $3}}')" != "go{GO_VERSION}" ]; then
  echo "GO_TOOLCHAIN_VERSION_MISMATCH" >&2
  exit 33
fi

current_commit=""
if [ -f {STATE_DIR}/source.commit ]; then
  current_commit="$(cat {STATE_DIR}/source.commit 2>/dev/null || true)"
fi
if [ ! -x {BINARY_PATH} ] || [ "$current_commit" != {q_commit} ]; then
  work="$(mktemp -d)"
  cleanup() {{ rm -rf "$work"; }}
  trap cleanup EXIT
  git -C "$work" init -q
  git -C "$work" remote add origin {q_repo}
  git -C "$work" fetch -q --depth=1 origin {q_commit}
  git -C "$work" checkout -q --detach FETCH_HEAD
  (
    cd "$work"
    CGO_ENABLED=0 GOTOOLCHAIN=local "$GO_BIN" build -trimpath -ldflags='-s -w' -o "$work/dnstt-server" ./dnstt-server
  )
  install -m 0755 "$work/dnstt-server" {BINARY_PATH}
  printf '%s\n' {q_commit} > {STATE_DIR}/source.commit
fi

if [ ! -s {STATE_DIR}/server.key ] || [ ! -s {STATE_DIR}/server.pub ]; then
  umask 077
  {BINARY_PATH} -gen-key -privkey-file {STATE_DIR}/server.key -pubkey-file {STATE_DIR}/server.pub
fi
chmod 0600 {STATE_DIR}/server.key
chmod 0644 {STATE_DIR}/server.pub

cat > /etc/systemd/system/{SERVICE_NAME} <<'UNIT'
[Unit]
Description=TwinPanel DNS Emergency DNSTT
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={BINARY_PATH} -udp {listen_addr} -privkey-file {STATE_DIR}/server.key {domain} 127.0.0.1:{int(upstream_port)}
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
s.settimeout(2.0)
try:
    s.connect(("127.0.0.1", {int(upstream_port)}))
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
printf 'GO_VERSION=%s\n' 'go{GO_VERSION}'
"""


def _health_script(upstream_port: int) -> str:
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
s.settimeout(2.0)
try:
    s.connect(("127.0.0.1", {int(upstream_port)}))
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


def _parse_lines(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in str(text or "").splitlines():
        if "=" in raw:
            key, value = raw.split("=", 1)
            result[key.strip().upper()] = value.strip()
    return result


def _mark_error(db: Session, node_id: int, message: str) -> None:
    row = _setting(db, node_id)
    if not row:
        return
    row.runtime_status = "error"
    row.last_error = str(message or "dns emergency failed")[:1800]
    row.checked_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.commit()


@router.get("/dns-emergency")
def inventory(db: Session = Depends(get_db)):
    nodes = (
        db.query(Node)
        .filter(Node.node_type == NodeType.EXIT, Node.retired_at.is_(None))
        .order_by(Node.id.asc())
        .all()
    )
    return {
        "ok": True,
        "engine": "dnstt",
        "source": {
            "repository": DNSTT_REPOSITORY,
            "commit": DNSTT_COMMIT,
            "go_version": GO_VERSION,
        },
        "nodes": [
            _setting_payload(node, _setting(db, node.id), _candidate_rows(db, node.id))
            for node in nodes
        ],
    }


@router.post("/dns-emergency/{node_id}/install")
async def install(node_id: int, payload: DnsEmergencyInstallIn, db: Session = Depends(get_db)):
    node = _exit_node(db, node_id)
    domain = _normalize_domain(payload.tunnel_domain, field_name="Tunnel Domain")
    nameserver = _normalize_domain(payload.nameserver_host, field_name="Nameserver") if payload.nameserver_host else None
    upstream_port = int(payload.upstream_port)

    candidates = _candidate_rows(db, node.id)
    if not candidates:
        raise HTTPException(
            status_code=409,
            detail="هیچ سرویس TCP شناخته‌شده‌ای برای DNS Emergency روی این Exit آماده نیست",
        )
    if upstream_port not in {int(item["port"]) for item in candidates}:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "پورت مقصد باید متعلق به یک سرویس TCP شناخته‌شده روی همین Exit باشد",
                "allowed_ports": [int(item["port"]) for item in candidates],
            },
        )

    row = _setting(db, node.id)
    if not row:
        row = DnsEmergencySetting(node_id=node.id)
        db.add(row)
    row.tunnel_domain = domain
    row.nameserver_host = nameserver
    row.upstream_port = upstream_port
    row.dnstt_commit = DNSTT_COMMIT
    row.runtime_status = "installing"
    row.last_error = None
    row.updated_at = datetime.utcnow()
    db.commit()

    try:
        conn = await _connect(node, db)
        try:
            result = await _run_script(conn, _install_script(node, domain, upstream_port))
        finally:
            conn.close()
            await conn.wait_closed()
    except Exception as exc:
        _mark_error(db, node.id, str(exc))
        raise HTTPException(status_code=502, detail={"message": "اتصال/نصب DNS Emergency ناموفق بود", "error": str(exc)[:1800]}) from exc

    parsed = _parse_lines(result.stdout)
    if int(getattr(result, "exit_status", 1) or 0) != 0:
        message = str(result.stderr or result.stdout or "dnstt install failed")
        _mark_error(db, node.id, message)
        raise HTTPException(status_code=502, detail={"message": "نصب DNS Emergency روی Exit ناموفق بود", "error": message[-1800:]})

    public_key = parsed.get("PUBLIC_KEY", "")
    if not public_key:
        _mark_error(db, node.id, "dnstt public key missing")
        raise HTTPException(status_code=502, detail="کلید عمومی DNSTT از نود دریافت نشد")

    row = _setting(db, node.id)
    if not row:
        raise HTTPException(status_code=500, detail="وضعیت DNS Emergency ذخیره نشد")
    row.public_key = public_key
    row.runtime_status = "online"
    row.last_error = None
    row.checked_at = datetime.utcnow()
    row.last_applied_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.commit()

    record_type = "AAAA" if ipaddress.ip_address(str(node.public_ip)).version == 6 else "A"
    return {
        "ok": True,
        **_setting_payload(node, row, _candidate_rows(db, node.id)),
        "dns_instructions": {
            "tunnel_domain": domain,
            "nameserver_host": nameserver,
            "exit_ip": node.public_ip,
            "records": ([
                {"type": record_type, "name": nameserver, "value": node.public_ip},
                {"type": "NS", "name": domain, "value": nameserver},
            ] if nameserver else []),
        },
    }


@router.post("/dns-emergency/{node_id}/health")
async def health(node_id: int, db: Session = Depends(get_db)):
    node = _exit_node(db, node_id)
    row = _setting(db, node.id)
    if not row or not row.upstream_port:
        raise HTTPException(status_code=409, detail="DNS Emergency روی این Exit نصب نشده است")

    try:
        conn = await _connect(node, db)
        try:
            result = await _run_script(conn, _health_script(int(row.upstream_port)))
        finally:
            conn.close()
            await conn.wait_closed()
    except Exception as exc:
        _mark_error(db, node.id, str(exc))
        raise HTTPException(status_code=502, detail={"message": "Health Check ناموفق بود", "error": str(exc)[:1800]}) from exc

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
        **_setting_payload(node, row, _candidate_rows(db, node.id)),
        "runtime": parsed,
    }


@router.delete("/dns-emergency/{node_id}")
async def remove(node_id: int, db: Session = Depends(get_db)):
    node = _exit_node(db, node_id)
    row = _setting(db, node.id)
    if not row:
        return {"ok": True, "node_id": node.id, "status": "not_installed"}

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
        raise HTTPException(status_code=502, detail={"message": "حذف DNS Emergency ناموفق بود", "error": str(exc)[:1800]}) from exc

    if int(getattr(result, "exit_status", 1) or 0) != 0:
        raise HTTPException(status_code=502, detail={"message": "حذف DNS Emergency ناموفق بود", "error": str(result.stderr or result.stdout or "")[-1800:]})

    row.runtime_status = "not_installed"
    row.last_error = None
    row.checked_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, **_setting_payload(node, row, _candidate_rows(db, node.id))}
