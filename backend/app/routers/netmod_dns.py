from __future__ import annotations

import base64
import ipaddress
import json
import shlex
from datetime import datetime
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..dnstt_artifact import stage_dnstt_binary
from ..dns_emergency_models import DnsEmergencySetting
from ..models import Node, NodeType
from .dns_emergency import DNSTT_COMMIT, DNSTT_REPOSITORY, _connect, _normalize_domain, _parse_lines, _run_script


router = APIRouter(
    prefix="/v1/settings/vpn",
    tags=["netmod-dns"],
    dependencies=[Depends(require_admin)],
)

ENGINE = "netmod_dns"
STATE_DIR = "/etc/twinpanel/netmod-dns"
DNSTT_BINARY_PATH = "/usr/local/bin/twinpanel-netmod-dnstt-server"
DNSTT_SERVICE = "twinpanel-netmod-dnstt.service"
SSH_SERVICE = "twinpanel-netmod-ssh.service"
NAT_SERVICE = "twinpanel-netmod-nat.service"
SSH_USER = "tpnetmod"
SSH_PORT = 2222
DNSTT_PORT = 5353
PASSWORD_PATH = f"{STATE_DIR}/netmod.password"
PUBLIC_KEY_PATH = f"{STATE_DIR}/server.pub"
PRIVATE_KEY_PATH = f"{STATE_DIR}/server.key"
SSHD_CONFIG_PATH = f"{STATE_DIR}/sshd_config"
NAT_SCRIPT_PATH = f"{STATE_DIR}/nat.sh"
NETMOD_AES_KEY = b"_netsyna_netmod_"
DEFAULT_RESOLVER = "8.8.8.8"
LEGACY_DNS_SERVICES = (
    "twinpanel-dnstt.service",
    "twinpanel-dnstt-iran.service",
    "twinpanel-masterdnsvpn.service",
)


class NetModDnsInstallIn(BaseModel):
    tunnel_domain: str = Field(min_length=4, max_length=253)
    nameserver_host: str | None = Field(default=None, max_length=253)


def _setting(db: Session, node_id: int) -> DnsEmergencySetting | None:
    return (
        db.query(DnsEmergencySetting)
        .filter(DnsEmergencySetting.node_id == int(node_id))
        .first()
    )


def _eligible_exit(db: Session, node_id: int) -> Node:
    node = (
        db.query(Node)
        .filter(Node.id == int(node_id), Node.retired_at.is_(None))
        .first()
    )
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    if node.node_type != NodeType.EXIT:
        raise HTTPException(status_code=400, detail="NetMod DNS فقط روی Exit Node نصب می‌شود")
    if str(node.agent_url or "") == "local://core":
        raise HTTPException(status_code=409, detail="NetMod DNS روی TwinPanel Local Core نصب نمی‌شود؛ یک Exit واقعی انتخاب کنید")
    try:
        parsed = ipaddress.ip_address(str(node.public_ip))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Public IP نود معتبر نیست") from exc
    if parsed.version != 4:
        raise HTTPException(status_code=409, detail="نسخه فعلی NetMod DNS فقط Exit دارای IPv4 را پشتیبانی می‌کند")
    return node


def _eligible_nodes(db: Session) -> list[Node]:
    return (
        db.query(Node)
        .filter(Node.node_type == NodeType.EXIT, Node.retired_at.is_(None))
        .order_by(Node.id.asc())
        .all()
    )


def _resolver(value: str) -> str:
    raw = str(value or "").strip()
    try:
        parsed = ipaddress.ip_address(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Resolver باید یک IP معتبر باشد") from exc
    if parsed.version != 4:
        raise HTTPException(status_code=422, detail="فعلاً Resolver IPv4 وارد کنید")
    return parsed.compressed


def _netmod_encrypt_payload(payload: dict[str, str]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    padder = padding.PKCS7(128).padder()
    padded = padder.update(raw) + padder.finalize()
    cipher = Cipher(algorithms.AES(NETMOD_AES_KEY), modes.ECB())
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return "nm-dns://" + base64.b64encode(encrypted).decode("ascii")


def _netmod_link(*, node: Node, setting: DnsEmergencySetting, resolver: str, password: str) -> tuple[str, dict[str, str]]:
    if not setting.tunnel_domain or not setting.public_key:
        raise HTTPException(status_code=409, detail="NetMod DNS هنوز آماده خروجی نیست")
    payload = {
        "ps": f"TwinPanel {node.name}",
        "addr": resolver,
        "ns": str(setting.tunnel_domain),
        "pubkey": str(setting.public_key),
        "user": SSH_USER,
        "pass": password,
    }
    return _netmod_encrypt_payload(payload), payload


def _payload(node: Node, setting: DnsEmergencySetting | None) -> dict[str, Any]:
    return {
        "node_id": int(node.id),
        "node_name": str(node.name),
        "public_ip": str(node.public_ip),
        "status": setting.runtime_status if setting else "not_installed",
        "tunnel_domain": setting.tunnel_domain if setting else None,
        "nameserver_host": setting.nameserver_host if setting else None,
        "public_key": setting.public_key if setting else None,
        "dnstt_commit": setting.dnstt_commit if setting and setting.dnstt_commit else DNSTT_COMMIT,
        "last_error": setting.last_error if setting else None,
        "checked_at": setting.checked_at.isoformat() + "Z" if setting and setting.checked_at else None,
        "last_applied_at": setting.last_applied_at.isoformat() + "Z" if setting and setting.last_applied_at else None,
        "client_ready": bool(
            setting
            and setting.runtime_status == "online"
            and setting.tunnel_domain
            and setting.public_key
        ),
    }


def _dns_records(node: Node, domain: str, nameserver: str | None) -> dict[str, Any]:
    records: list[dict[str, str]] = []
    if nameserver:
        records = [
            {"type": "A", "name": nameserver, "value": str(node.public_ip)},
            {"type": "NS", "name": domain, "value": nameserver},
        ]
    return {
        "tunnel_domain": domain,
        "nameserver_host": nameserver,
        "exit_ip": str(node.public_ip),
        "records": records,
    }


def _install_script(*, public_ip: str, domain: str) -> str:
    q_ip = shlex.quote(str(ipaddress.ip_address(public_ip)))
    q_domain = shlex.quote(domain)
    q_state = shlex.quote(STATE_DIR)
    q_binary = shlex.quote(DNSTT_BINARY_PATH)
    q_password = shlex.quote(PASSWORD_PATH)
    q_pub = shlex.quote(PUBLIC_KEY_PATH)
    q_priv = shlex.quote(PRIVATE_KEY_PATH)
    q_sshd = shlex.quote(SSHD_CONFIG_PATH)
    q_nat_script = shlex.quote(NAT_SCRIPT_PATH)
    legacy = " ".join(shlex.quote(item) for item in LEGACY_DNS_SERVICES)

    return f"""set -Eeuo pipefail
install -d -m 0700 {q_state}
test -x {q_binary} || {{ echo NETMOD_DNSTT_ARTIFACT_MISSING >&2; exit 34; }}
command -v /usr/sbin/sshd >/dev/null 2>&1 || {{ echo OPENSSH_SERVER_MISSING >&2; exit 35; }}
command -v iptables >/dev/null 2>&1 || {{ echo IPTABLES_MISSING >&2; exit 36; }}

# One DNS emergency engine owns this Exit. Stop older TwinPanel DNS engines but
# preserve their state/binaries for rollback until production acceptance.
systemctl disable --now {legacy} >/dev/null 2>&1 || true

if [ ! -s {q_priv} ] || [ ! -s {q_pub} ]; then
  umask 077
  {q_binary} -gen-key -privkey-file {q_priv} -pubkey-file {q_pub}
fi
chmod 0600 {q_priv}
chmod 0644 {q_pub}

if ! id -u {SSH_USER} >/dev/null 2>&1; then
  useradd --create-home --shell /bin/sh {SSH_USER}
fi

if [ ! -s {q_password} ]; then
  umask 077
  python3 - <<'PY' > {q_password}
import secrets
print(secrets.token_urlsafe(24))
PY
fi
chmod 0600 {q_password}
netmod_password="$(tr -d '\\r\\n' < {q_password})"
test -n "$netmod_password"
printf '%s:%s\\n' {SSH_USER} "$netmod_password" | chpasswd

install -d -m 0755 /run/sshd
cat > {q_sshd} <<'EOF'
Port {SSH_PORT}
ListenAddress 127.0.0.1
PasswordAuthentication yes
KbdInteractiveAuthentication no
PubkeyAuthentication no
PermitRootLogin no
UsePAM no
AllowUsers {SSH_USER}
AllowTcpForwarding yes
GatewayPorts no
X11Forwarding no
AllowAgentForwarding no
PermitTunnel no
PermitTTY no
PermitUserEnvironment no
ClientAliveInterval 30
ClientAliveCountMax 3
PidFile /run/twinpanel-netmod-sshd.pid
LogLevel ERROR
ForceCommand /usr/bin/sleep infinity
EOF
chmod 0600 {q_sshd}
/usr/sbin/sshd -t -f {q_sshd}

cat > /etc/systemd/system/{SSH_SERVICE} <<'UNIT'
[Unit]
Description=TwinPanel NetMod DNS internal SSH
After=network.target

[Service]
Type=simple
ExecStartPre=/usr/sbin/sshd -t -f {SSHD_CONFIG_PATH}
ExecStart=/usr/sbin/sshd -D -e -f {SSHD_CONFIG_PATH}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/{DNSTT_SERVICE} <<'UNIT'
[Unit]
Description=TwinPanel NetMod DNS DNSTT transport
After=network-online.target {SSH_SERVICE}
Wants=network-online.target
Requires={SSH_SERVICE}

[Service]
Type=simple
ExecStart={DNSTT_BINARY_PATH} -udp {public_ip}:{DNSTT_PORT} -privkey-file {PRIVATE_KEY_PATH} {domain} 127.0.0.1:{SSH_PORT}
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

cat > {q_nat_script} <<'EOF'
#!/bin/sh
set -eu
IP={public_ip}
COMMENT=TwinPanel-NetMod-DNS
TO_PORT={DNSTT_PORT}
rule_exists() {{
  iptables -t nat -C PREROUTING -p udp -d "$IP" --dport 53 -m comment --comment "$COMMENT" -j REDIRECT --to-ports "$TO_PORT" >/dev/null 2>&1
}}
case "${{1:-}}" in
  start)
    rule_exists || iptables -t nat -I PREROUTING 1 -p udp -d "$IP" --dport 53 -m comment --comment "$COMMENT" -j REDIRECT --to-ports "$TO_PORT"
    ;;
  stop)
    while rule_exists; do
      iptables -t nat -D PREROUTING -p udp -d "$IP" --dport 53 -m comment --comment "$COMMENT" -j REDIRECT --to-ports "$TO_PORT"
    done
    ;;
  check)
    rule_exists
    ;;
  *) exit 2 ;;
esac
EOF
chmod 0700 {q_nat_script}

cat > /etc/systemd/system/{NAT_SERVICE} <<'UNIT'
[Unit]
Description=TwinPanel NetMod DNS UDP/53 redirect
After=network-online.target {DNSTT_SERVICE}
Wants=network-online.target
Requires={DNSTT_SERVICE}

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart={NAT_SCRIPT_PATH} start
ExecStop={NAT_SCRIPT_PATH} stop

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable {SSH_SERVICE} {DNSTT_SERVICE} {NAT_SERVICE} >/dev/null
systemctl restart {SSH_SERVICE}
systemctl restart {DNSTT_SERVICE}
systemctl restart {NAT_SERVICE}
sleep 1

service_ssh="$(systemctl is-active {SSH_SERVICE} 2>/dev/null || true)"
service_dnstt="$(systemctl is-active {DNSTT_SERVICE} 2>/dev/null || true)"
service_nat="$(systemctl is-active {NAT_SERVICE} 2>/dev/null || true)"
ssh_listener=no
dnstt_listener=no
nat_rule=no
ss -H -ltnp 2>/dev/null | grep -F '127.0.0.1:{SSH_PORT} ' >/dev/null 2>&1 && ssh_listener=yes || true
ss -H -lunp 2>/dev/null | grep -F '{public_ip}:{DNSTT_PORT} ' >/dev/null 2>&1 && dnstt_listener=yes || true
{q_nat_script} check >/dev/null 2>&1 && nat_rule=yes || true

python3 - <<'PY'
import socket
s=socket.create_connection(("127.0.0.1", {SSH_PORT}), timeout=3)
try:
    banner=s.recv(64)
    if not banner.startswith(b"SSH-"):
        raise SystemExit("SSH_BANNER_MISSING")
finally:
    s.close()
PY

printf 'SSH_SERVICE=%s\\n' "$service_ssh"
printf 'DNSTT_SERVICE=%s\\n' "$service_dnstt"
printf 'NAT_SERVICE=%s\\n' "$service_nat"
printf 'SSH_LISTENER=%s\\n' "$ssh_listener"
printf 'DNSTT_LISTENER=%s\\n' "$dnstt_listener"
printf 'NAT_RULE=%s\\n' "$nat_rule"
printf 'PUBLIC_KEY='
tr -d '\\r\\n' < {q_pub}
printf '\\n'
printf 'DOMAIN=%s\\n' {q_domain}
printf 'LISTEN=%s:{DNSTT_PORT}\\n' {q_ip}
"""


def _health_script(*, public_ip: str) -> str:
    q_nat_script = shlex.quote(NAT_SCRIPT_PATH)
    return f"""set -u
ssh_service="$(systemctl is-active {SSH_SERVICE} 2>/dev/null || true)"
dnstt_service="$(systemctl is-active {DNSTT_SERVICE} 2>/dev/null || true)"
nat_service="$(systemctl is-active {NAT_SERVICE} 2>/dev/null || true)"
ssh_listener=no
dnstt_listener=no
nat_rule=no
key=no
password=no
ss -H -ltnp 2>/dev/null | grep -F '127.0.0.1:{SSH_PORT} ' >/dev/null 2>&1 && ssh_listener=yes || true
ss -H -lunp 2>/dev/null | grep -F '{public_ip}:{DNSTT_PORT} ' >/dev/null 2>&1 && dnstt_listener=yes || true
{q_nat_script} check >/dev/null 2>&1 && nat_rule=yes || true
[ -s {PUBLIC_KEY_PATH} ] && key=yes
[ -s {PASSWORD_PATH} ] && password=yes
printf 'SSH_SERVICE=%s\\n' "$ssh_service"
printf 'DNSTT_SERVICE=%s\\n' "$dnstt_service"
printf 'NAT_SERVICE=%s\\n' "$nat_service"
printf 'SSH_LISTENER=%s\\n' "$ssh_listener"
printf 'DNSTT_LISTENER=%s\\n' "$dnstt_listener"
printf 'NAT_RULE=%s\\n' "$nat_rule"
printf 'KEY=%s\\n' "$key"
printf 'PASSWORD=%s\\n' "$password"
printf 'PUBLIC_KEY='
[ -s {PUBLIC_KEY_PATH} ] && tr -d '\\r\\n' < {PUBLIC_KEY_PATH}
printf '\\n'
"""


def _mark_error(db: Session, node_id: int, message: str) -> None:
    row = _setting(db, node_id)
    if not row:
        return
    row.runtime_status = "error"
    row.last_error = str(message or "NetMod DNS failed")[:1800]
    row.checked_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.commit()


@router.get("/netmod-dns")
def inventory(db: Session = Depends(get_db)):
    nodes = [node for node in _eligible_nodes(db) if str(node.agent_url or "") != "local://core"]
    return {
        "ok": True,
        "engine": ENGINE,
        "source": {"repository": DNSTT_REPOSITORY, "commit": DNSTT_COMMIT},
        "default_resolver": DEFAULT_RESOLVER,
        "resolver_examples": ["8.8.8.8", "1.1.1.1", "9.9.9.9", "208.67.222.222"],
        "nodes": [_payload(node, _setting(db, node.id)) for node in nodes],
    }


@router.post("/netmod-dns/{node_id}/install")
async def install(node_id: int, payload: NetModDnsInstallIn, db: Session = Depends(get_db)):
    node = _eligible_exit(db, node_id)
    domain = _normalize_domain(payload.tunnel_domain, field_name="Tunnel Domain")
    nameserver = _normalize_domain(payload.nameserver_host, field_name="Nameserver") if payload.nameserver_host else None

    row = _setting(db, node.id)
    if not row:
        row = DnsEmergencySetting(node_id=node.id)
        db.add(row)
    row.tunnel_domain = domain
    row.nameserver_host = nameserver
    row.upstream_port = SSH_PORT
    row.dnstt_commit = DNSTT_COMMIT
    row.runtime_status = "installing"
    row.last_error = None
    row.updated_at = datetime.utcnow()
    db.commit()

    artifact_meta: dict[str, str] = {}
    try:
        conn = await _connect(node, db)
        try:
            artifact_meta = await stage_dnstt_binary(conn, DNSTT_BINARY_PATH)
            result = await _run_script(conn, _install_script(public_ip=str(node.public_ip), domain=domain))
        finally:
            conn.close()
            await conn.wait_closed()
    except Exception as exc:
        _mark_error(db, node.id, str(exc))
        raise HTTPException(status_code=502, detail={"message": "نصب NetMod DNS روی Exit ناموفق بود", "error": str(exc)[:1800]}) from exc

    parsed = _parse_lines(result.stdout)
    if int(getattr(result, "exit_status", 1) or 0) != 0:
        message = str(result.stderr or result.stdout or "NetMod DNS install failed")
        _mark_error(db, node.id, message)
        raise HTTPException(status_code=502, detail={"message": "نصب NetMod DNS روی Exit ناموفق بود", "error": message[-1800:]})

    ok = all(
        parsed.get(key) == expected
        for key, expected in (
            ("SSH_SERVICE", "active"),
            ("DNSTT_SERVICE", "active"),
            ("NAT_SERVICE", "active"),
            ("SSH_LISTENER", "yes"),
            ("DNSTT_LISTENER", "yes"),
            ("NAT_RULE", "yes"),
        )
    )
    public_key = parsed.get("PUBLIC_KEY", "")
    if not ok or not public_key:
        message = "; ".join(f"{key.lower()}={parsed.get(key, 'unknown')}" for key in ("SSH_SERVICE", "DNSTT_SERVICE", "NAT_SERVICE", "SSH_LISTENER", "DNSTT_LISTENER", "NAT_RULE", "PUBLIC_KEY"))
        _mark_error(db, node.id, message)
        raise HTTPException(status_code=502, detail={"message": "Health اولیه NetMod DNS ناموفق بود", "error": message})

    row = _setting(db, node.id)
    if not row:
        raise HTTPException(status_code=500, detail="وضعیت NetMod DNS ذخیره نشد")
    row.public_key = public_key
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
        "dns_instructions": _dns_records(node, domain, nameserver),
    }


@router.post("/netmod-dns/{node_id}/health")
async def health(node_id: int, db: Session = Depends(get_db)):
    node = _eligible_exit(db, node_id)
    row = _setting(db, node.id)
    if not row or not row.tunnel_domain:
        raise HTTPException(status_code=409, detail="NetMod DNS روی این Exit نصب نشده است")

    try:
        conn = await _connect(node, db)
        try:
            result = await _run_script(conn, _health_script(public_ip=str(node.public_ip)))
        finally:
            conn.close()
            await conn.wait_closed()
    except Exception as exc:
        _mark_error(db, node.id, str(exc))
        raise HTTPException(status_code=502, detail={"message": "Health Check ناموفق بود", "error": str(exc)[:1800]}) from exc

    parsed = _parse_lines(result.stdout)
    ok = (
        int(getattr(result, "exit_status", 1) or 0) == 0
        and parsed.get("SSH_SERVICE") == "active"
        and parsed.get("DNSTT_SERVICE") == "active"
        and parsed.get("NAT_SERVICE") == "active"
        and parsed.get("SSH_LISTENER") == "yes"
        and parsed.get("DNSTT_LISTENER") == "yes"
        and parsed.get("NAT_RULE") == "yes"
        and parsed.get("KEY") == "yes"
        and parsed.get("PASSWORD") == "yes"
    )
    row.runtime_status = "online" if ok else "error"
    row.public_key = parsed.get("PUBLIC_KEY") or row.public_key
    row.last_error = None if ok else "; ".join(
        f"{key.lower()}={parsed.get(key, 'unknown')}"
        for key in ("SSH_SERVICE", "DNSTT_SERVICE", "NAT_SERVICE", "SSH_LISTENER", "DNSTT_LISTENER", "NAT_RULE", "KEY", "PASSWORD")
    )
    row.checked_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": ok, **_payload(node, row), "runtime": parsed}


@router.get("/netmod-dns/{node_id}/config")
async def client_config(
    node_id: int,
    resolver: str = Query(DEFAULT_RESOLVER, min_length=3, max_length=64),
    db: Session = Depends(get_db),
):
    node = _eligible_exit(db, node_id)
    row = _setting(db, node.id)
    if not row or row.runtime_status != "online" or not row.tunnel_domain or not row.public_key:
        raise HTTPException(status_code=409, detail="NetMod DNS روی این Exit Online نیست")
    resolver_ip = _resolver(resolver)

    try:
        conn = await _connect(node, db)
        try:
            result = await _run_script(conn, f"set -Eeuo pipefail; test -s {shlex.quote(PASSWORD_PATH)}; printf 'PASSWORD='; tr -d '\\r\\n' < {shlex.quote(PASSWORD_PATH)}; printf '\\n'")
        finally:
            conn.close()
            await conn.wait_closed()
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"message": "دریافت اطلاعات NetMod ناموفق بود", "error": str(exc)[:1200]}) from exc

    if int(getattr(result, "exit_status", 1) or 0) != 0:
        raise HTTPException(status_code=502, detail="رمز داخلی NetMod از Exit دریافت نشد")
    password = _parse_lines(result.stdout).get("PASSWORD", "")
    if not password or len(password) > 256 or any(ch.isspace() for ch in password):
        raise HTTPException(status_code=502, detail="رمز داخلی NetMod معتبر نیست")

    link, payload = _netmod_link(node=node, setting=row, resolver=resolver_ip, password=password)
    return {
        "ok": True,
        "engine": ENGINE,
        "node_id": int(node.id),
        "resolver": resolver_ip,
        "secret": True,
        "nm_dns": link,
        "format": "nm-dns",
        "parameters": {
            "name": payload["ps"],
            "resolver": payload["addr"],
            "domain": payload["ns"],
            "public_key": payload["pubkey"],
            "username": payload["user"],
        },
    }


@router.delete("/netmod-dns/{node_id}")
async def remove(node_id: int, db: Session = Depends(get_db)):
    node = _eligible_exit(db, node_id)
    row = _setting(db, node.id)
    script = f"""set -u
[ -x {shlex.quote(NAT_SCRIPT_PATH)} ] && {shlex.quote(NAT_SCRIPT_PATH)} stop >/dev/null 2>&1 || true
systemctl disable --now {NAT_SERVICE} {DNSTT_SERVICE} {SSH_SERVICE} >/dev/null 2>&1 || true
rm -f /etc/systemd/system/{NAT_SERVICE} /etc/systemd/system/{DNSTT_SERVICE} /etc/systemd/system/{SSH_SERVICE}
systemctl daemon-reload
printf 'REMOVED=yes\\n'
"""
    try:
        conn = await _connect(node, db)
        try:
            result = await _run_script(conn, script)
        finally:
            conn.close()
            await conn.wait_closed()
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"message": "حذف NetMod DNS ناموفق بود", "error": str(exc)[:1800]}) from exc

    if int(getattr(result, "exit_status", 1) or 0) != 0:
        raise HTTPException(status_code=502, detail={"message": "حذف NetMod DNS ناموفق بود", "error": str(result.stderr or result.stdout or "")[-1800:]})

    if row:
        row.runtime_status = "not_installed"
        row.last_error = None
        row.checked_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
        db.commit()
        return {"ok": True, **_payload(node, row)}
    return {"ok": True, "node_id": int(node.id), "status": "not_installed"}
