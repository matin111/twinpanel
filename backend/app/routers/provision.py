

from ..services.public_urls import api_base_url
from fastapi import Request
import asyncio
import base64
import json
import secrets
import shlex
import os
from pathlib import Path
from datetime import datetime
from textwrap import dedent
import subprocess

import asyncssh
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Tunnel, TunnelPeerState, TunnelStatus
from ..deps import require_admin
from ..models import Node, NodeAccess, NodeProtocolConfig, NodeStatus, NodeType
from ..mother_access import get_or_create_l2tp_psk
from ..protocol_identity import (
    get_or_create_cisco_identity,
    get_or_create_openvpn_server_identity,
    get_or_create_wireguard_identity,
    identity_fingerprint,
    is_openvpn_central_pki_enabled,
)

router = APIRouter(prefix="/v1/provision", tags=["provision"], dependencies=[Depends(require_admin)])


class SSHBase(BaseModel):
    host: str
    port: int = Field(default=22, ge=1, le=65535)
    username: str = "root"
    password: str


class TestIn(SSHBase):
    pass


class ProtocolSettings(BaseModel):
    install_cisco: bool = True
    cisco_port: int = Field(default=443, ge=1, le=65535)
    install_openvpn: bool = True
    openvpn_port: int = Field(default=1194, ge=1, le=65535)
    openvpn_transport: str = "udp"
    install_wireguard: bool = True
    wireguard_port: int = Field(default=51820, ge=1, le=65535)
    install_l2tp: bool = True
    install_v2ray: bool = True
    xray_port: int = Field(default=8443, ge=1, le=65535)

    @model_validator(mode="after")
    def validate_ports(self):
        if self.openvpn_transport not in ("udp", "tcp"):
            raise ValueError("OpenVPN transport must be udp or tcp")
        requested = []
        if self.install_cisco:
            requested += [(self.cisco_port, "tcp", "Cisco"), (self.cisco_port, "udp", "Cisco DTLS")]
        if self.install_openvpn:
            requested.append((self.openvpn_port, self.openvpn_transport, "OpenVPN"))
        if self.install_wireguard:
            requested.append((self.wireguard_port, "udp", "WireGuard"))
        if self.install_l2tp:
            requested += [(500, "udp", "IPsec"), (4500, "udp", "IPsec NAT-T"), (1701, "udp", "L2TP")]
        if self.install_v2ray:
            requested.append((self.xray_port, "tcp", "Xray"))
        seen = {}
        for port, proto, name in requested:
            key = (port, proto)
            if key in seen and seen[key] != name:
                raise ValueError(f"Port conflict: {name} and {seen[key]} use {proto.upper()} {port}")
            seen[key] = name
        return self


class InstallIn(SSHBase, ProtocolSettings):
    name: str
    node_type: NodeType
    country_code: str = "IR"
    capacity_users: int = Field(default=1000, gt=0)


class RepairProtocolsIn(SSHBase, ProtocolSettings):
    node_id: int = Field(gt=0)


class RepairSavedProtocolsIn(ProtocolSettings):
    node_id: int = Field(gt=0)


class ProtocolControlIn(BaseModel):
    node_id: int = Field(gt=0)
    protocol: str | None = None


class SaveNodeAccessIn(SSHBase):
    node_id: int = Field(gt=0)


class NodeActionIn(BaseModel):
    node_id: int = Field(gt=0)


class UpgradeAgentIn(BaseModel):
    node_id: int = Field(gt=0)
    host: str | None = None
    port: int = Field(default=22, ge=1, le=65535)
    username: str = "root"
    password: str


async def ssh_connect(p: SSHBase):
    try:
        return await asyncssh.connect(p.host, port=p.port, username=p.username, password=p.password, known_hosts=None, connect_timeout=12, login_timeout=12)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"اتصال SSH ناموفق بود: {exc}")


NODE_KEY_DIR = Path("/var/lib/vpnshop/node-keys")


def _node_key_path(node_id: int) -> Path:
    NODE_KEY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(NODE_KEY_DIR, 0o700)
    except OSError:
        pass
    return NODE_KEY_DIR / f"node-{node_id}.key"


def _get_node_access(db: Session, node_id: int) -> NodeAccess | None:
    return db.query(NodeAccess).filter(NodeAccess.node_id == node_id).first()


async def _ensure_node_key_on_remote(conn, db: Session, node: Node, ssh_port: int, ssh_username: str) -> NodeAccess:
    key_path = _node_key_path(node.id)
    if not key_path.exists():
        key = asyncssh.generate_private_key("ssh-ed25519")
        key_path.write_bytes(key.export_private_key(format_name="openssh"))
        os.chmod(key_path, 0o600)
        public_key = key.export_public_key(format_name="openssh").decode().strip()
    else:
        key = asyncssh.read_private_key(str(key_path))
        public_key = key.export_public_key(format_name="openssh").decode().strip()

    await cmd(conn, "mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys")
    encoded = base64.b64encode(public_key.encode()).decode()
    await cmd(conn, f"PUB=$(printf '%s' {shlex.quote(encoded)} | base64 -d); grep -qxF \"$PUB\" ~/.ssh/authorized_keys || printf '%s\\n' \"$PUB\" >> ~/.ssh/authorized_keys")

    fingerprint = (await cmd(conn, f"printf '%s\\n' {shlex.quote(public_key)} | ssh-keygen -lf - 2>/dev/null | awk '{{print $2}}'", check=False)).strip() or None
    access = _get_node_access(db, node.id)
    if not access:
        access = NodeAccess(node_id=node.id, ssh_port=ssh_port, ssh_username=ssh_username, private_key_path=str(key_path), public_key_fingerprint=fingerprint)
        db.add(access)
    else:
        access.ssh_port = ssh_port
        access.ssh_username = ssh_username
        access.private_key_path = str(key_path)
        access.public_key_fingerprint = fingerprint
        access.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(access)
    return access


async def ssh_connect_saved(node: Node, db: Session):
    access = _get_node_access(db, node.id)
    if not access:
        raise HTTPException(status_code=409, detail="دسترسی امن این سرور ثبت نشده است. یک‌بار «ثبت دسترسی سرور» را انجام دهید.")
    key_path = Path(access.private_key_path)
    if not key_path.exists():
        raise HTTPException(status_code=409, detail="کلید دسترسی این سرور پیدا نشد. دسترسی را دوباره ثبت کنید.")
    try:
        return await asyncssh.connect(node.public_ip, port=access.ssh_port, username=access.ssh_username, client_keys=[str(key_path)], known_hosts=None, connect_timeout=12, login_timeout=12)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"اتصال ذخیره‌شده SSH ناموفق بود: {exc}")


@router.get("/node-access/{node_id}")
def node_access_status(node_id: int, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    access = _get_node_access(db, node_id)
    return {"configured": bool(access and Path(access.private_key_path).exists()), "node_id": node_id, "host": node.public_ip, "port": access.ssh_port if access else 22, "username": access.ssh_username if access else "root", "fingerprint": access.public_key_fingerprint if access else None}


@router.post("/save-node-access")
async def save_node_access(payload: SaveNodeAccessIn, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == payload.node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    conn = await ssh_connect(payload)

    try:
        # TWINPANEL_NODE_MANAGED_PREFLIGHT_V1
        from ..managed_preflight import (
            preflight_managed_artifacts_on_conn,
        )

        preflight = (
            await preflight_managed_artifacts_on_conn(
                conn,
                db,
                node.id,
                cleanup=True,
            )
        )

        access = await _ensure_node_key_on_remote(
            conn,
            db,
            node,
            payload.port,
            payload.username,
        )

        return {
            "ok": True,
            "configured": True,
            "node_id": node.id,
            "port": access.ssh_port,
            "username": access.ssh_username,
            "fingerprint": access.public_key_fingerprint,
            "preflight": preflight,
            "message": "دسترسی امن سرور ذخیره شد",
        }

    finally:
        conn.close()
        await conn.wait_closed()


async def cmd(conn, command: str, timeout: int = 180, check: bool = True):
    try:
        r = await asyncio.wait_for(conn.run(command, check=False), timeout=timeout)
    except asyncio.TimeoutError:
        raise RuntimeError("مهلت اجرای دستور تمام شد")
    if check and r.exit_status != 0:
        msg = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(msg or f"command failed: {command}")
    return (r.stdout or "").strip()


@router.post("/test")
async def test_connection(payload: TestIn):
    conn = await ssh_connect(payload)
    try:
        return {
            "ok": True,
            "hostname": await cmd(conn, "hostname"),
            "os_name": await cmd(conn, ". /etc/os-release && printf '%s' \"$NAME\""),
            "os_version": await cmd(conn, ". /etc/os-release && printf '%s' \"$VERSION_ID\""),
            "cpu_cores": int(await cmd(conn, "nproc")),
            "memory_mb": int(await cmd(conn, "awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo")),
            "disk_gb": int(await cmd(conn, "df -BG / | awk 'NR==2 {gsub(/G/,\"\",$2); print $2}'")),
        }
    finally:
        conn.close(); await conn.wait_closed()


async def listener(conn, port: int, proto: str) -> bool:
    mode = "ltn" if proto == "tcp" else "lun"
    return bool((await cmd(conn, f"ss -H -{mode} 'sport = :{int(port)}'", check=False)).strip())


async def active(conn, *services: str) -> bool:
    for service in services:
        if (await cmd(conn, f"systemctl is-active {shlex.quote(service)}", check=False)).strip() == "active":
            return True
    return False


async def preflight(conn, port: int, proto: str, label: str):
    if await listener(conn, port, proto):
        raise RuntimeError(f"پورت {port}/{proto.upper()} برای {label} از قبل در حال استفاده است")


async def ufw_allow(conn, port: int, proto: str):
    if "Status: active" in await cmd(conn, "ufw status 2>/dev/null | head -1", check=False):
        await cmd(conn, f"ufw allow {port}/{proto} >/dev/null", check=False)


def save_config(db: Session, node_id: int, protocol: str, *, port=None, port_text="", transport="", service="", ok=False, error=None):
    item = db.query(NodeProtocolConfig).filter(NodeProtocolConfig.node_id == node_id, NodeProtocolConfig.protocol == protocol).first()
    if not item:
        item = NodeProtocolConfig(node_id=node_id, protocol=protocol); db.add(item)
    item.port = port
    item.port_text = port_text or (str(port) if port else "")
    item.transport = transport
    item.service_name = service
    item.status = "online" if ok else "error"
    item.last_error = error
    item.checked_at = datetime.utcnow()


# TWINPANEL_TUNNEL_RUNTIME_V1
async def ensure_base(conn):
    await cmd(conn, "export DEBIAN_FRONTEND=noninteractive; apt-get update -y >/dev/null && apt-get install -y python3 python3-venv python3-pip curl ca-certificates iproute2 iptables iputils-ping openssl wireguard-tools kmod >/dev/null", timeout=900)
    await cmd(conn, "printf 'net.ipv4.ip_forward=1\n' > /etc/sysctl.d/99-twinpanel.conf && sysctl -p /etc/sysctl.d/99-twinpanel.conf >/dev/null")
    await cmd(conn, "modprobe wireguard >/dev/null 2>&1 || true", check=False)
    await cmd(conn, "command -v wg >/dev/null 2>&1")


async def install_cisco(
    conn,
    port: int,
    db: Session | None = None,
    node: Node | None = None,
    repair: bool = False,
):
    await cmd(
        conn,
        "export DEBIAN_FRONTEND=noninteractive; "
        "apt-get install -y ocserv >/dev/null",
        timeout=600,
    )

    await cmd(
        conn,
        "mkdir -p /etc/ocserv; "
        "touch /etc/ocserv/ocpasswd; "
        "chmod 600 /etc/ocserv/ocpasswd",
    )

    central = None
    use_central = False

    if (
        db is not None
        and node is not None
        and node.node_type == NodeType.EXIT
    ):
        central = get_or_create_cisco_identity(
            db
        )

        central_fp = identity_fingerprint(
            central["certificate"]
        )

        if not repair:
            use_central = True

        else:
            state = await cmd(
                conn,
                (
                    "if [ -f "
                    "/etc/twinpanel/managed-identities/cisco ]; "
                    "then echo managed; "
                    "elif [ ! -s /etc/ocserv/server-cert.pem ] "
                    "|| [ ! -s /etc/ocserv/server-key.pem ]; "
                    "then echo missing; "
                    "else "
                    "openssl x509 "
                    "-in /etc/ocserv/server-cert.pem "
                    "-outform DER 2>/dev/null | "
                    "sha256sum | cut -c1-16; "
                    "fi"
                ),
                check=False,
            )

            state = state.strip()

            use_central = (
                state in (
                    "managed",
                    "missing",
                    central_fp,
                )
            )

    if use_central and central:
        cert_b64 = base64.b64encode(
            central["certificate"].encode()
        ).decode()

        key_b64 = base64.b64encode(
            central["private_key"].encode()
        ).decode()

        await cmd(
            conn,
            (
                "printf '%s' "
                f"{shlex.quote(cert_b64)} | "
                "base64 -d > "
                "/etc/ocserv/server-cert.pem && "
                "printf '%s' "
                f"{shlex.quote(key_b64)} | "
                "base64 -d > "
                "/etc/ocserv/server-key.pem && "
                "chmod 644 "
                "/etc/ocserv/server-cert.pem && "
                "chmod 600 "
                "/etc/ocserv/server-key.pem"
            ),
        )

        await cmd(
            conn,
            r'''
set -e

CERT_PUB=$(
  openssl x509 \
    -in /etc/ocserv/server-cert.pem \
    -pubkey -noout |
  openssl pkey \
    -pubin \
    -outform DER 2>/dev/null |
  sha256sum |
  awk '{print $1}'
)

KEY_PUB=$(
  openssl pkey \
    -in /etc/ocserv/server-key.pem \
    -pubout \
    -outform DER 2>/dev/null |
  sha256sum |
  awk '{print $1}'
)

test "$CERT_PUB" = "$KEY_PUB"

mkdir -p /etc/twinpanel/managed-identities
chmod 700 /etc/twinpanel/managed-identities
touch /etc/twinpanel/managed-identities/cisco
''',
        )

    else:
        await cmd(
            conn,
            (
                "test -f /etc/ocserv/server-key.pem || "
                "openssl req -x509 -newkey rsa:2048 "
                "-nodes -days 3650 "
                "-subj '/CN=TwinPanel VPN' "
                "-keyout /etc/ocserv/server-key.pem "
                "-out /etc/ocserv/server-cert.pem "
                ">/dev/null 2>&1"
            ),
        )

    config = f'''auth = "plain[/etc/ocserv/ocpasswd]"
tcp-port = {port}
udp-port = {port}
run-as-user = nobody
run-as-group = daemon
socket-file = /run/ocserv-socket
use-occtl = true
occtl-socket-file = /run/occtl.socket
server-cert = /etc/ocserv/server-cert.pem
server-key = /etc/ocserv/server-key.pem
isolate-workers = true
max-clients = 2048
max-same-clients = 8
keepalive = 30
dpd = 60
mobile-dpd = 300
try-mtu-discovery = true
device = vpns
ipv4-network = 10.91.0.0
ipv4-netmask = 255.255.255.0
dns = 1.1.1.1
dns = 8.8.8.8
route = default
'''

    b64 = base64.b64encode(
        config.encode()
    ).decode()

    await cmd(
        conn,
        (
            f"printf '%s' {shlex.quote(b64)} | "
            "base64 -d > /etc/ocserv/ocserv.conf"
        ),
    )

    await cmd(
        conn,
        "ocserv -t -c /etc/ocserv/ocserv.conf",
    )

    await ufw_allow(conn, port, "tcp")
    await ufw_allow(conn, port, "udp")

    await cmd(
        conn,
        "systemctl enable ocserv >/dev/null && "
        "systemctl restart ocserv",
    )

    await asyncio.sleep(1)

    ok = (
        await active(conn, "ocserv")
        and await listener(
            conn,
            port,
            "tcp",
        )
    )

    return (
        ok,
        None
        if ok
        else "ocserv یا Listener بالا نیامد",
    )


async def stage_openvpn_central_identity(
    conn,
    db: Session,
    node: Node,
):
    """
    Central OpenVPN identity را فقط روی Exit آماده می‌کند.

    فایل‌های فعال OpenVPN تغییر نمی‌کنند.
    سرویس Restart نمی‌شود.
    """

    identity = (
        get_or_create_openvpn_server_identity(
            db,
            node.id,
        )
    )

    files = {
        "/etc/openvpn/twinpanel-central/ca.crt":
            identity["ca_certificate"],

        "/etc/openvpn/twinpanel-central/server.crt":
            identity["server_certificate"],

        "/etc/openvpn/twinpanel-central/server.key":
            identity["server_private_key"],
    }

    await cmd(
        conn,
        (
            "mkdir -p "
            "/etc/openvpn/twinpanel-central && "
            "chmod 700 "
            "/etc/openvpn/twinpanel-central"
        ),
    )

    for path, content in files.items():
        encoded = base64.b64encode(
            content.encode()
        ).decode()

        await cmd(
            conn,
            (
                f"printf '%s' "
                f"{shlex.quote(encoded)} | "
                f"base64 -d > "
                f"{shlex.quote(path)}"
            ),
        )

    await cmd(
        conn,
        (
            "chmod 644 "
            "/etc/openvpn/twinpanel-central/ca.crt "
            "/etc/openvpn/twinpanel-central/server.crt && "
            "chmod 600 "
            "/etc/openvpn/twinpanel-central/server.key"
        ),
    )

    return {
        "ok": True,
        "path": "/etc/openvpn/twinpanel-central",
        "central_enabled": (
            is_openvpn_central_pki_enabled(db)
        ),
    }


async def install_openvpn(conn, port: int, transport: str):
    await cmd(conn, "export DEBIAN_FRONTEND=noninteractive; apt-get install -y openvpn easy-rsa >/dev/null", timeout=600)
    await cmd(conn, "mkdir -p /etc/openvpn/server /etc/openvpn/easy-rsa; test -f /etc/openvpn/easy-rsa/easyrsa || cp -a /usr/share/easy-rsa/* /etc/openvpn/easy-rsa/")
    await cmd(conn, "cd /etc/openvpn/easy-rsa && test -d pki || ./easyrsa init-pki >/dev/null")
    await cmd(conn, "cd /etc/openvpn/easy-rsa && test -f pki/ca.crt || EASYRSA_BATCH=1 EASYRSA_REQ_CN='TwinPanel CA' ./easyrsa build-ca nopass >/dev/null", timeout=300)
    await cmd(conn, "cd /etc/openvpn/easy-rsa && test -f pki/issued/server.crt || EASYRSA_BATCH=1 ./easyrsa build-server-full server nopass >/dev/null", timeout=300)
    proto = "udp" if transport == "udp" else "tcp-server"

    # TWINPANEL_SAFE_OPENVPN_REPAIR_V4
    connect_script = (
        "#!/bin/sh\n"
        "set -eu\n"
        "CN=\"${common_name:-}\"\n"
        "case \"$CN\" in\n"
        "  \"\"|*[!A-Za-z0-9_.@-]*) exit 1 ;;\n"
        "esac\n"
        "test ! -e \"/etc/openvpn/twinpanel-disabled/$CN\"\n"
    )

    script_b64 = base64.b64encode(
        connect_script.encode()
    ).decode()

    await cmd(
        conn,
        "mkdir -p /etc/openvpn/twinpanel-disabled; "
        "chmod 755 /etc/openvpn/twinpanel-disabled; "
        f"printf '%s' {shlex.quote(script_b64)} | "
        "base64 -d > "
        "/usr/local/sbin/twinpanel-openvpn-client-connect; "
        "chmod 755 "
        "/usr/local/sbin/twinpanel-openvpn-client-connect",
    )

    config = f'''port {port}
proto {proto}
dev tun
ca /etc/openvpn/easy-rsa/pki/ca.crt
cert /etc/openvpn/easy-rsa/pki/issued/server.crt
key /etc/openvpn/easy-rsa/pki/private/server.key
dh none
ecdh-curve prime256v1
topology subnet
server 10.92.0.0 255.255.255.0
keepalive 10 60
persist-key
persist-tun
user nobody
group nogroup
verb 3
data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305
auth SHA256
# TWINPANEL_OPENVPN_CONTROL_V1
script-security 2
client-connect /usr/local/sbin/twinpanel-openvpn-client-connect
management /run/openvpn-server/twinpanel-mgmt.sock unix
management-client-user root
# END_TWINPANEL_OPENVPN_CONTROL_V1
'''
    b64 = base64.b64encode(config.encode()).decode()
    await cmd(conn, f"printf '%s' {shlex.quote(b64)} | base64 -d > /etc/openvpn/server/twinpanel.conf")
    await ufw_allow(conn, port, transport)
    # TWINPANEL_MANAGED_IDENTITY_OPENVPN_V1
    await cmd(
        conn,
        "mkdir -p /etc/twinpanel/managed-identities && "
        "chmod 700 /etc/twinpanel/managed-identities && "
        "touch /etc/twinpanel/managed-identities/openvpn"
    )

    await cmd(conn, "systemctl enable openvpn-server@twinpanel >/dev/null && systemctl restart openvpn-server@twinpanel")
    await asyncio.sleep(1)
    ok = await active(conn, "openvpn-server@twinpanel") and await listener(conn, port, transport)
    return ok, None if ok else "OpenVPN service یا Listener بالا نیامد"


async def install_wireguard(
    conn,
    port: int,
    db: Session | None = None,
    node: Node | None = None,
    repair: bool = False,
):
    await cmd(
        conn,
        "export DEBIAN_FRONTEND=noninteractive; "
        "apt-get install -y wireguard-tools >/dev/null",
        timeout=600,
    )

    await cmd(
        conn,
        "mkdir -p /etc/wireguard; "
        "chmod 700 /etc/wireguard",
    )

    central = None
    use_central = False

    if (
        db is not None
        and node is not None
        and node.node_type == NodeType.EXIT
    ):
        central = (
            get_or_create_wireguard_identity(
                db
            )
        )

        if not repair:
            use_central = True

        else:
            state = await cmd(
                conn,
                (
                    "if [ -f "
                    "/etc/twinpanel/managed-identities/wireguard ]; "
                    "then echo managed; "
                    "elif [ ! -s "
                    "/etc/wireguard/wg-access0.key ]; "
                    "then echo missing; "
                    "else "
                    "wg pubkey < "
                    "/etc/wireguard/wg-access0.key "
                    "2>/dev/null || true; "
                    "fi"
                ),
                check=False,
            )

            state = state.strip()

            use_central = (
                state in (
                    "managed",
                    "missing",
                    central["public_key"],
                )
            )

    if use_central and central:
        key_b64 = base64.b64encode(
            (
                central["private_key"].strip()
                + "\n"
            ).encode()
        ).decode()

        await cmd(
            conn,
            (
                f"printf '%s' {shlex.quote(key_b64)} | "
                "base64 -d > "
                "/etc/wireguard/wg-access0.key && "
                "chmod 600 "
                "/etc/wireguard/wg-access0.key"
            ),
        )

        remote_public = await cmd(
            conn,
            (
                "wg pubkey < "
                "/etc/wireguard/wg-access0.key"
            ),
        )

        if (
            remote_public.strip()
            != central["public_key"].strip()
        ):
            raise RuntimeError(
                "Central WireGuard identity verification failed"
            )

        await cmd(
            conn,
            (
                "mkdir -p "
                "/etc/twinpanel/managed-identities && "
                "chmod 700 "
                "/etc/twinpanel/managed-identities && "
                "touch "
                "/etc/twinpanel/managed-identities/wireguard"
            ),
        )

    else:
        await cmd(
            conn,
            (
                "test -f "
                "/etc/wireguard/wg-access0.key || "
                "(umask 077; "
                "wg genkey > "
                "/etc/wireguard/wg-access0.key)"
            ),
        )

    key = await cmd(
        conn,
        "cat /etc/wireguard/wg-access0.key",
    )

    # TWINPANEL_SAFE_WIREGUARD_REPAIR_V5
    # Preserve all existing wg-access0 Peer blocks.

    existing_peers = await cmd(
        conn,
        (
            "if [ -s /etc/wireguard/wg-access0.conf ]; then "
            "sed -n '/^\\[Peer\\]/,$p' "
            "/etc/wireguard/wg-access0.conf; "
            "fi"
        ),
        check=False,
    )

    config = f'''[Interface]
Address = 10.93.0.1/24
ListenPort = {port}
PrivateKey = {key}
SaveConfig = false
'''

    if existing_peers.strip():
        config = (
            config.rstrip()
            + "\n\n"
            + existing_peers.strip()
            + "\n"
        )

    b64 = base64.b64encode(
        config.encode()
    ).decode()

    await cmd(
        conn,
        (
            "set -e; "
            "TMP=$(mktemp "
            "/etc/wireguard/wgtmpXXXXXXXX.conf); "

            f"printf '%s' {shlex.quote(b64)} "
            "| base64 -d > \"$TMP\"; "

            "chmod 600 \"$TMP\"; "

            "wg-quick strip "
            "\"$TMP\" >/dev/null; "

            "if [ -f "
            "/etc/wireguard/wg-access0.conf ]; then "
            "cp -a "
            "/etc/wireguard/wg-access0.conf "
            "/etc/wireguard/wg-access0.conf."
            "bak-repair-$(date +%Y%m%d-%H%M%S); "
            "fi; "

            "mv \"$TMP\" "
            "/etc/wireguard/wg-access0.conf; "

            "chmod 600 "
            "/etc/wireguard/wg-access0.conf"
        ),
    )

    await ufw_allow(
        conn,
        port,
        "udp",
    )

    await cmd(
        conn,
        (
            "systemctl enable "
            "wg-quick@wg-access0 >/dev/null; "

            "if ip link show wg-access0 "
            ">/dev/null 2>&1; then "

            "TMP=$(mktemp /run/wgaccessXXXXXXXX); "
            "wg-quick strip "
            "/etc/wireguard/wg-access0.conf "
            "> \"$TMP\"; "

            "wg syncconf wg-access0 \"$TMP\"; "
            "rm -f \"$TMP\"; "

            "else "
            "systemctl start "
            "wg-quick@wg-access0; "
            "fi"
        ),
    )

    await asyncio.sleep(1)

    ok = (
        bool(
            (
                await cmd(
                    conn,
                    "wg show wg-access0",
                    check=False,
                )
            ).strip()
        )
        and await listener(
            conn,
            port,
            "udp",
        )
    )

    return (
        ok,
        None
        if ok
        else "WireGuard interface یا Listener بالا نیامد",
    )


# TWINPANEL_CENTRAL_L2TP_PSK_V1
async def install_l2tp(conn, psk: str):
    await cmd(conn, "export DEBIAN_FRONTEND=noninteractive; apt-get install -y strongswan xl2tpd ppp >/dev/null", timeout=600)

    psk = str(psk or "").strip()
    if not psk:
        raise RuntimeError("Central L2TP PSK is empty")
    configs = {
        "/etc/ipsec.conf": '''config setup
  uniqueids=no

conn twinpanel-l2tp
  type=transport
  authby=secret
  pfs=no
  auto=add
  keyingtries=3
  rekey=no
  left=%defaultroute
  leftprotoport=17/1701
  right=%any
  rightprotoport=17/%any
''',
        "/etc/ipsec.secrets": (
            f"%any %any : PSK 0x{psk.encode('utf-8').hex()}\n"
        ),
        "/etc/xl2tpd/xl2tpd.conf": '''[global]
port = 1701

[lns default]
ip range = 10.94.0.10-10.94.0.250
local ip = 10.94.0.1
require authentication = yes
require chap = yes
refuse pap = yes
pppoptfile = /etc/ppp/options.xl2tpd
length bit = yes
''',
        "/etc/ppp/options.xl2tpd": '''require-mschap-v2
ms-dns 1.1.1.1
ms-dns 8.8.8.8
auth
mtu 1200
mru 1200
proxyarp
connect-delay 5000
''',
    }
    for path, content in configs.items():
        b64 = base64.b64encode(content.encode()).decode()
        await cmd(conn, f"mkdir -p $(dirname {shlex.quote(path)}); printf '%s' {shlex.quote(b64)} | base64 -d > {shlex.quote(path)}")
    await cmd(conn, "chmod 600 /etc/ipsec.secrets; touch /etc/ppp/chap-secrets; chmod 600 /etc/ppp/chap-secrets")
    for port in (500, 4500, 1701): await ufw_allow(conn, port, "udp")
    await cmd(conn, "systemctl restart strongswan-starter || systemctl restart strongswan", check=False)
    # TWINPANEL_MANAGED_IDENTITY_L2TP_V1
    await cmd(
        conn,
        "mkdir -p /etc/twinpanel/managed-identities && "
        "chmod 700 /etc/twinpanel/managed-identities && "
        "touch /etc/twinpanel/managed-identities/l2tp"
    )

    await cmd(conn, "systemctl enable xl2tpd >/dev/null && systemctl restart xl2tpd")
    await asyncio.sleep(1)
    ok = (await active(conn, "strongswan-starter", "strongswan")) and (await active(conn, "xl2tpd")) and all([await listener(conn,500,"udp"), await listener(conn,4500,"udp"), await listener(conn,1701,"udp")])
    return ok, None if ok else "strongSwan/xl2tpd یا پورت‌های L2TP/IPsec آماده نیست", psk


async def install_xray(conn, port: int):
    await cmd(conn, "tmp=$(mktemp); curl -fsSL https://github.com/XTLS/Xray-install/raw/main/install-release.sh -o \"$tmp\" && bash \"$tmp\" install; rc=$?; rm -f \"$tmp\"; exit $rc", timeout=600)
    config = {
        "log": {"loglevel": "warning"},
        "api": {
            "tag": "api",
            "services": [
                "HandlerService",
                "LoggerService",
                "StatsService",
            ],
        },
        "stats": {},
        "policy": {
            "levels": {
                "0": {
                    "statsUserUplink": True,
                    "statsUserDownlink": True,
                }
            },
            "system": {
                "statsInboundUplink": True,
                "statsInboundDownlink": True,
            },
        },
        "inbounds": [
            {
                "tag": "vless-in",
                "listen": "0.0.0.0",
                "port": port,
                "protocol": "vless",
                "settings": {
                    "clients": [],
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "none",
                },
            },
            {
                "tag": "api",
                "listen": "127.0.0.1",
                "port": 10085,
                "protocol": "dokodemo-door",
                "settings": {
                    "address": "127.0.0.1",
                },
            },
        ],
        "outbounds": [
            {
                "protocol": "freedom",
                "tag": "direct",
            }
        ],
        "routing": {
            "rules": [
                {
                    "type": "field",
                    "inboundTag": ["api"],
                    "outboundTag": "api",
                }
            ]
        },
    }
    b64 = base64.b64encode(
        json.dumps(config).encode()
    ).decode()

    merge_py = r"""
import json
import os

old_path = "/usr/local/etc/xray/config.json"
new_path = "/usr/local/etc/xray/config.json.twinpanel-new"

with open(new_path, "r", encoding="utf-8") as f:
    new_doc = json.load(f)

old_clients = []

if os.path.exists(old_path):
    try:
        with open(old_path, "r", encoding="utf-8") as f:
            old_doc = json.load(f)

        for inbound in old_doc.get("inbounds", []):
            if not isinstance(inbound, dict):
                continue

            if (
                inbound.get("tag") != "vless-in"
                or inbound.get("protocol") != "vless"
            ):
                continue

            clients = (
                inbound.get("settings", {})
                .get("clients", [])
            )

            if isinstance(clients, list):
                for client in clients:
                    if isinstance(client, dict):
                        old_clients.append(client)

    except Exception as exc:
        raise SystemExit(
            "existing Xray config cannot be safely read: "
            + repr(exc)
        )

# TWINPANEL_SAFE_XRAY_REPAIR_V4
email_to_id = {}
id_to_email = {}

for client in old_clients:
    client_id = str(
        client.get("id") or ""
    ).strip()

    email = str(
        client.get("email") or ""
    ).strip()

    if not client_id:
        raise SystemExit(
            "existing Xray client has no id"
        )

    if (
        email
        and email in email_to_id
        and email_to_id[email] != client_id
    ):
        raise SystemExit(
            "Xray duplicate email conflict"
        )

    if (
        client_id in id_to_email
        and id_to_email[client_id] != email
    ):
        raise SystemExit(
            "Xray duplicate id conflict"
        )

    if email:
        email_to_id[email] = client_id

    id_to_email[client_id] = email


targets = [
    inbound
    for inbound in new_doc.get("inbounds", [])
    if isinstance(inbound, dict)
    and inbound.get("tag") == "vless-in"
    and inbound.get("protocol") == "vless"
]

if len(targets) != 1:
    raise SystemExit(
        "new vless-in inbound not found uniquely"
    )

clients = (
    targets[0]
    .setdefault("settings", {})
    .setdefault("clients", [])
)

seen = set()

for client in clients:
    if not isinstance(client, dict):
        continue

    key = (
        str(client.get("email") or ""),
        str(client.get("id") or ""),
    )

    seen.add(key)

for client in old_clients:
    key = (
        str(client.get("email") or ""),
        str(client.get("id") or ""),
    )

    if key in seen:
        continue

    clients.append(client)
    seen.add(key)

with open(new_path, "w", encoding="utf-8") as f:
    json.dump(
        new_doc,
        f,
        ensure_ascii=False,
        indent=2,
    )
    f.write("\n")

print(
    "preserved_xray_clients=",
    len(old_clients),
)
"""

    merge_b64 = base64.b64encode(
        merge_py.encode()
    ).decode()

    await cmd(
        conn,
        "mkdir -p /usr/local/etc/xray; "
        f"printf '%s' {shlex.quote(b64)} "
        "| base64 -d "
        "> /usr/local/etc/xray/config.json.twinpanel-new; "
        f"printf '%s' {shlex.quote(merge_b64)} "
        "| base64 -d | python3; "
        "/usr/local/bin/xray run -test "
        "-config /usr/local/etc/xray/config.json.twinpanel-new; "
        "if [ -f /usr/local/etc/xray/config.json ]; then "
        "cp -a /usr/local/etc/xray/config.json "
        "/usr/local/etc/xray/config.json.bak-repair-$(date +%Y%m%d-%H%M%S); "
        "fi; "
        "install -o root -g root -m 0644 "
        "/usr/local/etc/xray/config.json.twinpanel-new "
        "/usr/local/etc/xray/config.json; "
        "rm -f /usr/local/etc/xray/config.json.twinpanel-new"
    )

    await ufw_allow(conn, port, "tcp")
    await cmd(
        conn,
        "systemctl enable xray >/dev/null "
        "&& systemctl restart xray"
    )
    await asyncio.sleep(1)
    # TWINPANEL_MANAGED_IDENTITY_XRAY_V1
    await cmd(
        conn,
        "mkdir -p /etc/twinpanel/managed-identities && "
        "chmod 700 /etc/twinpanel/managed-identities && "
        "touch /etc/twinpanel/managed-identities/v2ray"
    )

    ok = await active(conn, "xray") and await listener(conn, port, "tcp")
    return ok, None if ok else "Xray service یا Listener بالا نیامد"


def make_agent(node_id: int, api_base: str) -> str:
    # TWINPANEL_SHARED_AGENT_TEMPLATE_V1
    template_path = (
        Path(__file__).resolve().parent.parent
        / "twinpanel_agent.py.tpl"
    )

    if not template_path.exists():
        raise RuntimeError(
            f"Agent template not found: {template_path}"
        )

    text = template_path.read_text()

    api_base = str(
        api_base or ""
    ).strip().rstrip("/")

    if not api_base:
        raise RuntimeError(
            "public_api_base_unavailable"
        )

    return (
        text
        .replace(
            "__API_LITERAL__",
            repr(api_base),
        )
        .replace(
            "__NODE_ID__",
            str(int(node_id)),
        )
        .replace(
            "__SECRET_LITERAL__",
            repr(settings.node_agent_shared_secret),
        )
    )


async def _install_or_upgrade_agent(
    conn,
    node_id: int,
    api_base: str,
) -> dict:
    """
    Atomically installs the current agent code and restarts the systemd service.
    Existing agent.py is backed up before replacement.
    """
    agent = make_agent(
        node_id,
        api_base,
    ).encode()
    agent_b64 = base64.b64encode(agent).decode()

    await cmd(conn, "mkdir -p /opt/twinpanel-agent /var/lib/twinpanel-agent")

    # Ensure runtime dependencies exist.
    # TWINPANEL_AGENT_APT_LOCK_RETRY_V1
    #
    # Tunnel transports can start concurrently. Never let a temporary
    # unattended-upgrades/apt lock make Node Agent bootstrap fail.
    await cmd(
        conn,
        "export DEBIAN_FRONTEND=noninteractive; "
        "if ! command -v python3 >/dev/null 2>&1 "
        "|| ! dpkg -s python3-venv python3-pip iproute2 iputils-ping wireguard-tools "
        ">/dev/null 2>&1; then "
        "for TRY in $(seq 1 60); do "
        "apt-get update -y >/dev/null 2>&1 && break; "
        "[ \"$TRY\" -eq 60 ] && exit 75; "
        "sleep 2; "
        "done; "
        "for TRY in $(seq 1 60); do "
        "apt-get -o DPkg::Lock::Timeout=300 install -y "
        "python3 python3-venv python3-pip iproute2 iputils-ping wireguard-tools "
        ">/dev/null 2>&1 && break; "
        "[ \"$TRY\" -eq 60 ] && exit 76; "
        "sleep 2; "
        "done; "
        "fi",
        timeout=900,
    )

    await cmd(
        conn,
        "if [ ! -x /opt/twinpanel-agent/venv/bin/python ]; then "
        "python3 -m venv /opt/twinpanel-agent/venv; fi && "
        "if ! /opt/twinpanel-agent/venv/bin/python -c "
        "\"import httpx,psutil; "
        "assert httpx.__version__ == '0.28.1'; "
        "assert psutil.__version__ == '7.0.0'\" "
        ">/dev/null 2>&1; then "
        "/opt/twinpanel-agent/venv/bin/pip install --upgrade pip >/dev/null && "
        "/opt/twinpanel-agent/venv/bin/pip install "
        "httpx==0.28.1 psutil==7.0.0 >/dev/null; "
        "fi",
        timeout=600,
    )

    # Write new code to a temp file first, syntax-check it, then swap atomically.
    await cmd(
        conn,
        f"printf '%s' {shlex.quote(agent_b64)} | base64 -d > /opt/twinpanel-agent/agent.py.new",
    )
    await cmd(
        conn,
        "/opt/twinpanel-agent/venv/bin/python -m py_compile /opt/twinpanel-agent/agent.py.new",
    )
    await cmd(
        conn,
        "if [ -f /opt/twinpanel-agent/agent.py ]; then "
        "cp -f /opt/twinpanel-agent/agent.py /opt/twinpanel-agent/agent.py.bak; fi && "
        "mv -f /opt/twinpanel-agent/agent.py.new /opt/twinpanel-agent/agent.py && "
        "chmod 600 /opt/twinpanel-agent/agent.py",
    )

    service = dedent("""
    [Unit]
    Description=TwinPanel VPN Node Agent
    After=network-online.target
    Wants=network-online.target

    [Service]
    Type=simple
    User=root
    WorkingDirectory=/opt/twinpanel-agent
    ExecStart=/opt/twinpanel-agent/venv/bin/python /opt/twinpanel-agent/agent.py
    Restart=always
    RestartSec=5

    [Install]
    WantedBy=multi-user.target
    """).strip().encode()
    service_b64 = base64.b64encode(service).decode()

    await cmd(
        conn,
        f"printf '%s' {shlex.quote(service_b64)} | base64 -d > /etc/systemd/system/twinpanel-agent.service.new",
    )
    await cmd(
        conn,
        "mv -f /etc/systemd/system/twinpanel-agent.service.new "
        "/etc/systemd/system/twinpanel-agent.service && "
        "systemctl daemon-reload && "
        "systemctl enable twinpanel-agent.service >/dev/null && "
        "systemctl restart twinpanel-agent.service",
    )

    # Wait briefly and verify the service really stayed up.
    await asyncio.sleep(2)
    status = await cmd(conn, "systemctl is-active twinpanel-agent.service", check=False)
    if status.strip() != "active":
        journal = await cmd(
            conn,
            "journalctl -u twinpanel-agent.service -n 25 --no-pager",
            check=False,
        )
        raise RuntimeError(
            "Agent after restart is not active. "
            + (journal[-1800:] if journal else status)
        )

    pid = await cmd(
        conn,
        "systemctl show twinpanel-agent.service -p MainPID --value",
        check=False,
    )
    return {
        "service": "active",
        "pid": int(pid) if pid.isdigit() else None,
        "agent_path": "/opt/twinpanel-agent/agent.py",
        "backup_path": "/opt/twinpanel-agent/agent.py.bak",
    }


@router.post("/upgrade-agent")
async def upgrade_agent(
    payload: NodeActionIn,
    request: Request,
    db: Session = Depends(get_db),
):
    node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == payload.node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    conn = await ssh_connect_saved(node, db)
    try:
        os_id = await cmd(conn, ". /etc/os-release && printf '%s' \"$ID\"")
        if os_id not in ("ubuntu", "debian"):
            raise HTTPException(status_code=400, detail="فعلاً Upgrade Agent روی Ubuntu/Debian پشتیبانی می‌شود")
        hostname = await cmd(conn, "hostname", check=False)
        result = await _install_or_upgrade_agent(
            conn,
            node.id,
            api_base_url(db, request),
        )
        return {"ok": True, "node_id": node.id, "node_name": node.name, "host": node.public_ip, "hostname": hostname, "agent": result, "message": "Node Agent با موفقیت به‌روزرسانی شد"}
    finally:
        conn.close()
        await conn.wait_closed()


async def existing_ok(conn, protocol: str, p: ProtocolSettings):
    if protocol == "cisco": return await active(conn,"ocserv") and await listener(conn,p.cisco_port,"tcp")
    if protocol == "openvpn": return await active(conn,"openvpn-server@twinpanel") and await listener(conn,p.openvpn_port,p.openvpn_transport)
    if protocol == "wireguard": return bool((await cmd(conn,"wg show wg-access0",check=False)).strip()) and await listener(conn,p.wireguard_port,"udp")
    if protocol == "l2tp": return await active(conn,"xl2tpd") and await listener(conn,1701,"udp")
    if protocol == "v2ray": return await active(conn,"xray") and await listener(conn,p.xray_port,"tcp")
    return False


async def provision_protocols(conn, p: ProtocolSettings, db: Session, node: Node, repair=False):
    results, secrets_out = {}, {}

    async def run_one(name, port, proto, service, installer, port_text=""):
        if repair and await existing_ok(conn, name, p):
            ok, err = True, None
        else:
            if port is not None: await preflight(conn, port, proto, name)
            ok, err = await installer()
        results[name] = {"ok":ok,"port":port,"port_text":port_text or (str(port) if port else ""),"transport":proto,"error":err}
        save_config(db,node.id,name,port=port,port_text=port_text,transport=proto,service=service,ok=ok,error=err)

    if p.install_cisco:
        try:
            if not (repair and await existing_ok(conn,"cisco",p)): await preflight(conn,p.cisco_port,"udp","Cisco DTLS")
            await run_one("cisco",p.cisco_port,"tcp+udp","ocserv",lambda:install_cisco(
                conn,
                p.cisco_port,
                db,
                node,
                repair,
            ))
        except Exception as e:
            results["cisco"]={"ok":False,"port":p.cisco_port,"port_text":str(p.cisco_port),"transport":"tcp+udp","error":str(e)}; save_config(db,node.id,"cisco",port=p.cisco_port,transport="tcp+udp",service="ocserv",ok=False,error=str(e))
    if p.install_openvpn:
        try: await run_one("openvpn",p.openvpn_port,p.openvpn_transport,"openvpn-server@twinpanel",lambda:install_openvpn(conn,p.openvpn_port,p.openvpn_transport))
        except Exception as e: results["openvpn"]={"ok":False,"port":p.openvpn_port,"port_text":str(p.openvpn_port),"transport":p.openvpn_transport,"error":str(e)}; save_config(db,node.id,"openvpn",port=p.openvpn_port,transport=p.openvpn_transport,service="openvpn-server@twinpanel",ok=False,error=str(e))
    # TWINPANEL_AUTO_OPENVPN_CENTRAL_STAGE_V1
    #
    # Every healthy EXIT OpenVPN installation is automatically
    # prepared for Central PKI.
    #
    # While the feature flag is False this only stages files.
    # The active OpenVPN configuration is not changed.
    if (
        p.install_openvpn
        and node.node_type == NodeType.EXIT
        and bool(
            results.get(
                "openvpn",
                {},
            ).get("ok")
        )
    ):
        try:
            central_stage = (
                await stage_openvpn_central_identity(
                    conn,
                    db,
                    node,
                )
            )

            results["openvpn"][
                "central_pki_ready"
            ] = True

            results["openvpn"][
                "central_pki_enabled"
            ] = bool(
                central_stage.get(
                    "central_enabled",
                    False,
                )
            )

            results["openvpn"][
                "central_pki_path"
            ] = central_stage.get(
                "path"
            )

        except Exception as central_exc:
            results["openvpn"][
                "central_pki_ready"
            ] = False

            results["openvpn"][
                "central_pki_stage_error"
            ] = str(
                central_exc
            )[:900]

    if p.install_wireguard:
        try: await run_one("wireguard",p.wireguard_port,"udp","wg-quick@wg-access0",lambda:install_wireguard(
                conn,
                p.wireguard_port,
                db,
                node,
                repair,
            ))
        except Exception as e: results["wireguard"]={"ok":False,"port":p.wireguard_port,"port_text":str(p.wireguard_port),"transport":"udp","error":str(e)}; save_config(db,node.id,"wireguard",port=p.wireguard_port,transport="udp",service="wg-quick@wg-access0",ok=False,error=str(e))
    if p.install_l2tp:
        try:
            psk=get_or_create_l2tp_psk(db)

            if repair and await existing_ok(conn,"l2tp",p):
                # TWINPANEL_L2TP_PSK_SYNC_V1
                secret_line = (
                    f"%any %any : PSK "
                    f"0x{psk.encode('utf-8').hex()}\n"
                )
                secret_b64 = base64.b64encode(
                    secret_line.encode()
                ).decode()

                await cmd(
                    conn,
                    f"printf '%s' {shlex.quote(secret_b64)} | "
                    f"base64 -d > /etc/ipsec.secrets; "
                    f"chmod 600 /etc/ipsec.secrets; "
                    f"(ipsec rereadsecrets || "
                    f"systemctl restart strongswan-starter)",
                    timeout=60,
                )

                ok,err=True,None
            else:
                for x in (500,4500,1701):
                    await preflight(
                        conn,
                        x,
                        "udp",
                        "L2TP/IPsec",
                    )

                ok,err,psk=await install_l2tp(
                    conn,
                    psk,
                )
            results["l2tp"]={"ok":ok,"port":None,"port_text":"500/4500/1701","transport":"udp","error":err}; save_config(db,node.id,"l2tp",port_text="500/4500/1701",transport="udp",service="strongswan-starter + xl2tpd",ok=ok,error=err)
            if psk: secrets_out["l2tp_psk"]=psk
        except Exception as e: results["l2tp"]={"ok":False,"port":None,"port_text":"500/4500/1701","transport":"udp","error":str(e)}; save_config(db,node.id,"l2tp",port_text="500/4500/1701",transport="udp",service="strongswan-starter + xl2tpd",ok=False,error=str(e))
    if p.install_v2ray:
        try: await run_one("v2ray",p.xray_port,"tcp","xray",lambda:install_xray(conn,p.xray_port))
        except Exception as e: results["v2ray"]={"ok":False,"port":p.xray_port,"port_text":str(p.xray_port),"transport":"tcp","error":str(e)}; save_config(db,node.id,"v2ray",port=p.xray_port,transport="tcp",service="xray",ok=False,error=str(e))

    node.enable_cisco=bool(results.get("cisco",{}).get("ok")) if p.install_cisco else node.enable_cisco
    node.enable_openvpn=bool(results.get("openvpn",{}).get("ok")) if p.install_openvpn else node.enable_openvpn
    node.enable_wireguard=bool(results.get("wireguard",{}).get("ok")) if p.install_wireguard else node.enable_wireguard
    node.enable_l2tp=bool(results.get("l2tp",{}).get("ok")) if p.install_l2tp else node.enable_l2tp
    node.enable_v2ray=bool(results.get("v2ray",{}).get("ok")) if p.install_v2ray else node.enable_v2ray
    db.commit()
    selected={"cisco":p.install_cisco,"openvpn":p.install_openvpn,"wireguard":p.install_wireguard,"l2tp":p.install_l2tp,"v2ray":p.install_v2ray}
    failed=[k for k,v in selected.items() if v and not results.get(k,{}).get("ok")]
    return results, failed, secrets_out



# TWINPANEL_AUTO_EXIT_MOTHER_TUNNEL_V1
def _ensure_exit_mother_tunnel(
    db: Session,
    exit_node: Node,
) -> Tunnel | None:
    """
    Every EXIT node automatically gets one active tunnel
    to the local Mother/Core node.

    Iran relay nodes are not handled here.
    """

    if exit_node.node_type != NodeType.EXIT:
        return None

    mother = (
        db.query(Node).filter(Node.retired_at.is_(None))
        .filter(
            Node.agent_url == "local://core"
        )
        .first()
    )

    if not mother:
        # Do not break node provisioning if Mother has not
        # been bootstrapped yet.
        return None

    tunnel = (
        db.query(Tunnel)
        .filter(
            Tunnel.iran_node_id == mother.id,
            Tunnel.exit_node_id == exit_node.id,
        )
        .first()
    )

    if not tunnel:
        tunnel = Tunnel(
            iran_node_id=mother.id,
            exit_node_id=exit_node.id,
            transport="auto",
            priority=100,
            is_active=True,
            status=TunnelStatus.OFFLINE,
        )

        db.add(tunnel)
        db.flush()

    else:
        # Existing route must remain usable.
        tunnel.is_active = True

    # Ensure state rows exist for both peers.
    for peer_node_id in (
        mother.id,
        exit_node.id,
    ):
        state = (
            db.query(TunnelPeerState)
            .filter(
                TunnelPeerState.tunnel_id
                == tunnel.id,
                TunnelPeerState.node_id
                == peer_node_id,
            )
            .first()
        )

        if not state:
            db.add(
                TunnelPeerState(
                    tunnel_id=tunnel.id,
                    node_id=peer_node_id,
                )
            )

    db.commit()
    db.refresh(tunnel)

    return tunnel



# ============================================================
# TWINPANEL_TUNNEL_FABRIC_BASE_V1
# ============================================================

async def _install_tunnel_fabric_base(
    conn,
    node: Node,
) -> dict:

    async def read_int(
        command: str,
        default: int = 0,
    ) -> int:
        raw = (
            await cmd(
                conn,
                command,
                check=False,
            )
        ).strip()

        try:
            return int(
                raw.splitlines()[-1]
            )
        except Exception:
            return default


    cpu = max(
        1,
        await read_int(
            "nproc",
            1,
        ),
    )


    mem_kb = await read_int(
        (
            "awk "
            "'/MemTotal:/ "
            "{print $2; exit}' "
            "/proc/meminfo"
        ),
        0,
    )

    mem_mb = max(
        1,
        mem_kb // 1024,
    )


    disk_percent = await read_int(
        (
            "df -P / | "
            "awk 'NR==2 "
            "{gsub(/%/,\"\",$5); "
            "print $5}'"
        ),
        0,
    )


    default_if = (
        await cmd(
            conn,
            (
                "ip route show default | "
                "awk 'NR==1 {print $5}'"
            ),
            check=False,
        )
    ).strip()


    mtu = await read_int(
        (
            "DEV=$(ip route show default "
            "| awk 'NR==1 {print $5}'); "
            "[ -n \"$DEV\" ] && "
            "cat /sys/class/net/$DEV/mtu "
            "2>/dev/null || echo 1500"
        ),
        1500,
    )


    # --------------------------------------------------------
    # Capacity profile
    # --------------------------------------------------------

    if (
        cpu >= 4
        and mem_mb >= 4096
    ):
        profile = "high_capacity"

        desired_conntrack = 262144
        desired_backlog = 16384
        desired_syn_backlog = 8192

        desired_rmem = 33554432
        desired_wmem = 33554432

    elif (
        cpu >= 2
        and mem_mb >= 2048
    ):
        profile = "standard"

        desired_conntrack = 131072
        desired_backlog = 8192
        desired_syn_backlog = 4096

        desired_rmem = 16777216
        desired_wmem = 16777216

    else:
        profile = "conservative"

        desired_conntrack = 65536
        desired_backlog = 4096
        desired_syn_backlog = 2048

        desired_rmem = 8388608
        desired_wmem = 8388608


    # Never lower an existing stronger system setting.
    current_conntrack = await read_int(
        (
            "sysctl -n "
            "net.netfilter.nf_conntrack_max "
            "2>/dev/null || echo 0"
        ),
        0,
    )

    current_backlog = await read_int(
        (
            "sysctl -n "
            "net.core.netdev_max_backlog "
            "2>/dev/null || echo 0"
        ),
        0,
    )

    current_syn_backlog = await read_int(
        (
            "sysctl -n "
            "net.ipv4.tcp_max_syn_backlog "
            "2>/dev/null || echo 0"
        ),
        0,
    )

    current_rmem = await read_int(
        (
            "sysctl -n "
            "net.core.rmem_max "
            "2>/dev/null || echo 0"
        ),
        0,
    )

    current_wmem = await read_int(
        (
            "sysctl -n "
            "net.core.wmem_max "
            "2>/dev/null || echo 0"
        ),
        0,
    )


    conntrack_max = max(
        desired_conntrack,
        current_conntrack,
    )

    backlog = max(
        desired_backlog,
        current_backlog,
    )

    syn_backlog = max(
        desired_syn_backlog,
        current_syn_backlog,
    )

    rmem = max(
        desired_rmem,
        current_rmem,
    )

    wmem = max(
        desired_wmem,
        current_wmem,
    )


    script = f"""
set -eu

export DEBIAN_FRONTEND=noninteractive

MISSING=""

for PKG in \
    iproute2 \
    iptables \
    nftables \
    conntrack \
    ethtool
do

    dpkg -s "$PKG" \
        >/dev/null 2>&1 \
        || MISSING="$MISSING $PKG"

done


if [ -n "$MISSING" ]; then

    OK=0

    for TRY in 1 2 3
    do
        if apt-get update -qq
        then
            OK=1
            break
        fi

        sleep 3
    done

    [ "$OK" = "1" ]

    apt-get install \
        -y \
        -qq \
        $MISSING \
        >/dev/null
fi


install -d -m 0755 \
    /etc/twinpanel/fabric \
    /var/lib/twinpanel-fabric \
    /run/twinpanel-fabric


modprobe tun \
    2>/dev/null \
    || true

modprobe nf_conntrack \
    2>/dev/null \
    || true


cat > /etc/sysctl.d/99-twinpanel-tunnel-fabric.conf <<'EOF'
# TwinPanel Tunnel Fabric Base V1

net.ipv4.ip_forward = 1

net.core.somaxconn = {backlog}
net.core.netdev_max_backlog = {backlog}

net.core.rmem_max = {rmem}
net.core.wmem_max = {wmem}

net.ipv4.tcp_rmem = 4096 262144 {rmem}
net.ipv4.tcp_wmem = 4096 262144 {wmem}

net.ipv4.tcp_max_syn_backlog = {syn_backlog}

net.ipv4.tcp_mtu_probing = 1

net.ipv4.tcp_keepalive_time = 60
net.ipv4.tcp_keepalive_intvl = 10
net.ipv4.tcp_keepalive_probes = 5

net.netfilter.nf_conntrack_max = {conntrack_max}
EOF


sysctl -p \
    /etc/sysctl.d/99-twinpanel-tunnel-fabric.conf \
    >/dev/null


cat > /etc/twinpanel/fabric/node.conf <<'EOF'
FABRIC_VERSION=1
NODE_ID={int(node.id)}
NODE_TYPE={getattr(node.node_type, "value", node.node_type)}
PROFILE={profile}
CPU={cpu}
MEMORY_MB={mem_mb}
MTU={mtu}
CONNTRACK_MAX={conntrack_max}
EOF


cat > /usr/local/sbin/twinpanel-fabric-prepare <<'SH'
#!/bin/sh
set -eu

install -d -m 0755 \
    /run/twinpanel-fabric \
    /var/lib/twinpanel-fabric

modprobe tun \
    2>/dev/null \
    || true

modprobe nf_conntrack \
    2>/dev/null \
    || true

sysctl -p \
    /etc/sysctl.d/99-twinpanel-tunnel-fabric.conf \
    >/dev/null

touch \
    /run/twinpanel-fabric/ready
SH


chmod 0755 \
    /usr/local/sbin/twinpanel-fabric-prepare


cat > /etc/systemd/system/twinpanel-tunnel-fabric.service <<'UNIT'
[Unit]
Description=TwinPanel Tunnel Fabric Base
After=network-online.target
Wants=network-online.target
Before=twinpanel-agent.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/twinpanel-fabric-prepare
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT


systemctl daemon-reload

systemctl enable \
    twinpanel-tunnel-fabric.service \
    >/dev/null

systemctl restart \
    twinpanel-tunnel-fabric.service
"""


    await cmd(
        conn,
        script,
        timeout=360,
    )


    service = (
        await cmd(
            conn,
            (
                "systemctl is-active "
                "twinpanel-tunnel-fabric.service"
            ),
            check=False,
        )
    ).strip()


    if service != "active":

        journal = await cmd(
            conn,
            (
                "journalctl "
                "-u twinpanel-tunnel-fabric.service "
                "-n 40 "
                "--no-pager"
            ),
            check=False,
        )

        raise RuntimeError(
            (
                "Tunnel Fabric Base "
                "فعال نشد: "
            )
            + journal[-1800:]
        )


    ready = (
        await cmd(
            conn,
            (
                "test -f "
                "/run/twinpanel-fabric/ready "
                "&& echo yes || echo no"
            ),
            check=False,
        )
    ).strip()


    conntrack_count = await read_int(
        (
            "cat "
            "/proc/sys/net/netfilter/"
            "nf_conntrack_count "
            "2>/dev/null || echo 0"
        ),
        0,
    )


    return {
        "ok": True,
        "version": 1,

        "service":
            service,

        "ready":
            ready == "yes",

        "profile":
            profile,

        "cpu":
            cpu,

        "memory_mb":
            mem_mb,

        "disk_percent":
            disk_percent,

        "default_interface":
            default_if or None,

        "mtu":
            mtu,

        "conntrack_count":
            conntrack_count,

        "conntrack_max":
            conntrack_max,

        "netdev_backlog":
            backlog,

        "tcp_syn_backlog":
            syn_backlog,

        "node_id":
            int(node.id),

        "node_type":
            getattr(
                node.node_type,
                "value",
                str(node.node_type),
            ),
    }



# ============================================================
# TWINPANEL_TUNNEL_FABRIC_PANEL_API_V1
# ============================================================

@router.post("/install-fabric")
async def install_tunnel_fabric(
    payload: NodeActionIn,
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
        raise HTTPException(
            status_code=404,
            detail="سرور پیدا نشد",
        )

    if (
        getattr(node, "is_mother", False)
        or str(node.agent_url or "") == "local://core"
        or str(node.public_ip or "").strip()
        in {"127.0.0.1", "localhost"}
    ):
        raise HTTPException(
            status_code=400,
            detail="Tunnel Fabric روی سرور پنل نصب نمی‌شود",
        )

    conn = await ssh_connect_saved(
        node,
        db,
    )

    try:
        result = await _install_tunnel_fabric_base(
            conn,
            node,
        )

        return {
            "ok": True,
            "node_id": node.id,
            "node_name": node.name,
            "fabric": result,
            "message": "Tunnel Fabric نصب و بررسی شد",
        }

    finally:
        conn.close()
        await conn.wait_closed()


@router.get("/fabric-status/{node_id}")
async def tunnel_fabric_status(
    node_id: int,
    db: Session = Depends(get_db),
):
    node = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == node_id,
        )
        .first()
    )

    if not node:
        raise HTTPException(
            status_code=404,
            detail="سرور پیدا نشد",
        )

    if (
        getattr(node, "is_mother", False)
        or str(node.agent_url or "") == "local://core"
    ):
        return {
            "ok": True,
            "node_id": node.id,
            "installed": False,
            "skipped": True,
            "reason": "mother",
        }

    conn = await ssh_connect_saved(
        node,
        db,
    )

    try:
        service = (
            await cmd(
                conn,
                "systemctl is-active twinpanel-tunnel-fabric.service",
                check=False,
            )
        ).strip()

        enabled = (
            await cmd(
                conn,
                "systemctl is-enabled twinpanel-tunnel-fabric.service",
                check=False,
            )
        ).strip()

        ready = (
            await cmd(
                conn,
                "test -f /run/twinpanel-fabric/ready && echo yes || echo no",
                check=False,
            )
        ).strip()

        config = (
            await cmd(
                conn,
                "cat /etc/twinpanel/fabric/node.conf 2>/dev/null || true",
                check=False,
            )
        ).strip()

        return {
            "ok": service == "active",
            "node_id": node.id,
            "node_name": node.name,
            "installed": service == "active",
            "service": service or "not-installed",
            "enabled": enabled == "enabled",
            "ready": ready == "yes",
            "config": config,
        }

    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/install")
async def install_node(
    payload: InstallIn,
    request: Request,
    db: Session = Depends(get_db),
):
    if db.query(Node).filter(Node.retired_at.is_(None)).filter(Node.name==payload.name).first(): raise HTTPException(status_code=409,detail="نام سرور قبلاً ثبت شده است")
    # TWINPANEL_IRAN_TUNNEL_ONLY
    # Iran nodes are relay/tunnel nodes only.
    # User-facing VPN protocols must never be provisioned here.
    if payload.node_type == NodeType.IRAN:
        payload.install_cisco = False
        payload.install_openvpn = False
        payload.install_wireguard = False
        payload.install_l2tp = False
        payload.install_v2ray = False

    conn=await ssh_connect(payload); node=None
    try:
        os_id=await cmd(conn,". /etc/os-release && printf '%s' \"$ID\"")
        if os_id not in ("ubuntu","debian"): raise HTTPException(status_code=400,detail="فعلاً Ubuntu/Debian پشتیبانی می‌شود")
        await ensure_base(conn)
        node=Node(name=payload.name,node_type=payload.node_type,country_code="IR" if payload.node_type==NodeType.IRAN else payload.country_code.upper(),public_ip=payload.host,agent_url=f"https://{payload.host}:9443",status=NodeStatus.OFFLINE,capacity_users=payload.capacity_users,enable_cisco=False,enable_openvpn=False,enable_wireguard=False,enable_l2tp=False,enable_v2ray=False)
        db.add(node); db.commit(); db.refresh(node)
        results, failed, secrets_out = await provision_protocols(
            conn,
            payload,
            db,
            node,
            False,
        )

        # TWINPANEL_AUTO_PROTOCOL_REPAIR_V2
        # Retry failed Exit protocols once. Healthy protocols are skipped
        # by provision_protocols(..., repair=True).
        auto_repair_attempted = False

        if node.node_type == NodeType.EXIT and failed:
            auto_repair_attempted = True
            await asyncio.sleep(2)

            (
                repair_results,
                repair_failed,
                repair_secrets,
            ) = await provision_protocols(
                conn,
                payload,
                db,
                node,
                True,
            )

            results = repair_results
            failed = repair_failed
            secrets_out.update(repair_secrets)

        # TWINPANEL_INSTALL_FINAL_HEALTH_V2
        # Final live service/listener health after install or automatic repair.
        if node.node_type == NodeType.EXIT:
            stored = _protocol_settings_from_db(db, node.id)

            selected_protocols = [
                name
                for name, enabled in {
                    "cisco": payload.install_cisco,
                    "openvpn": payload.install_openvpn,
                    "wireguard": payload.install_wireguard,
                    "l2tp": payload.install_l2tp,
                    "v2ray": payload.install_v2ray,
                }.items()
                if enabled
            ]

            await asyncio.sleep(2)

            final_failed = []

            for protocol in selected_protocols:
                try:
                    health = await _protocol_live_health(
                        conn,
                        protocol,
                        stored.get(protocol),
                    )
                except Exception as exc:
                    health = {
                        "ok": False,
                        "service": "unknown",
                        "listeners": {},
                        "error": str(exc),
                    }

                _save_live_health(
                    db,
                    node,
                    protocol,
                    health,
                )

                if protocol in results:
                    results[protocol]["health"] = health

                if not health.get("ok"):
                    final_failed.append(protocol)

            db.commit()
            failed = final_failed

        agent=await _install_or_upgrade_agent(
            conn,
            node.id,
            api_base_url(db, request),
        )
        await _ensure_node_key_on_remote(
            conn,
            db,
            node,
            payload.port,
            payload.username,
        )

        # TWINPANEL_TUNNEL_FABRIC_AUTO_INSTALL_V1
        fabric = {
            "ok": False,
            "service": "not_installed",
        }

        try:
            fabric = await _install_tunnel_fabric_base(
                conn,
                node,
            )

        except Exception as exc:
            fabric = {
                "ok": False,
                "service": "failed",
                "error":
                    str(exc)[:1800],
            }

            if "tunnel_fabric" not in failed:
                failed.append(
                    "tunnel_fabric"
                )


        # TWINPANEL_AUTO_QUOTA_AFTER_NODE_INSTALL_V1
        quota_sync = {
            "ok": True,
            "skipped": True,
            "reason": "iran_tunnel_only",
        }

        if node.node_type == NodeType.EXIT:
            project_root = (
                Path(__file__)
                .resolve()
                .parents[2]
            )

            quota_script = (
                project_root
                / "quota_bootstrap_v1.py"
            )

            quota_python = (
                project_root
                / "venv"
                / "bin"
                / "python"
            )

            try:
                proc = await asyncio.to_thread(
                    subprocess.run,
                    [
                        str(quota_python),
                        str(quota_script),
                        str(node.id),
                    ],
                    cwd=str(project_root),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=300,
                    check=False,
                )

                quota_output = (
                    proc.stdout or ""
                )[-4000:]

                quota_sync = {
                    "ok": proc.returncode == 0,
                    "returncode":
                        proc.returncode,
                    "output":
                        quota_output,
                }

                if proc.returncode != 0:
                    if "quota" not in failed:
                        failed.append("quota")

            except Exception as exc:
                quota_sync = {
                    "ok": False,
                    "error": str(exc)[:500],
                }

                if "quota" not in failed:
                    failed.append("quota")

        # TWINPANEL_INSTALLED_NODE_SUBSCRIPTION_AUTOSYNC_CALL_V1
        #
        # Every successfully installed Node is synchronized with
        # existing subscriptions. Iran Nodes only receive membership;
        # Exit Nodes also receive missing user credentials.
        subscription_sync = {
            "ok": True,
            "skipped": True,
            "reason": "not_run",
        }

        try:
            from .account_delivery import (
                sync_installed_node_to_subscriptions,
            )

            subscription_sync = (
                await sync_installed_node_to_subscriptions(
                    db,
                    node,
                )
            )

        except Exception as exc:
            db.rollback()

            subscription_sync = {
                "ok": False,
                "error":
                    str(exc)[:1200],
            }

        # TWINPANEL_MANUAL_IRAN_EXIT_TUNNEL_V2
        # Tunnel creation is controlled from Admin -> Tunnels.
        # The control/API server must never be used automatically
        # as the VPN traffic entry point.
        return {
            "ok": not failed,
            "node_id": node.id,
            "node_name": node.name,
            "status":
                "installed"
                if not failed
                else "partial",
            "protocols": results,
            "failed_protocols": failed,
            "one_time_secrets":
                secrets_out,
            "agent": agent,
            "quota": quota_sync,
            "subscription_sync": subscription_sync,
            "fabric": fabric,
            "access_saved": True,
            "message":
                "همه سرویس‌های انتخاب‌شده سالم هستند"
                if not failed
                else "برخی سرویس‌ها خطا دارند",
        }
    finally:
        conn.close(); await conn.wait_closed()



PROTOCOL_NAMES = {
    "cisco": "Cisco / OpenConnect",
    "openvpn": "OpenVPN",
    "wireguard": "WireGuard",
    "l2tp": "L2TP / IPsec",
    "v2ray": "V2Ray / Xray",
}


def _protocol_settings_from_db(db: Session, node_id: int) -> dict[str, NodeProtocolConfig]:
    return {
        item.protocol: item
        for item in db.query(NodeProtocolConfig)
        .filter(NodeProtocolConfig.node_id == node_id)
        .all()
    }


async def _service_state(conn, service: str) -> str:
    state = (await cmd(conn, f"systemctl is-active {shlex.quote(service)}", check=False)).strip()
    return state or "unknown"


async def _protocol_live_health(conn, protocol: str, item: NodeProtocolConfig | None) -> dict:
    if protocol == "cisco":
        port = int(item.port if item and item.port else 443)
        service = await _service_state(conn, "ocserv")
        tcp = await listener(conn, port, "tcp")
        udp = await listener(conn, port, "udp")
        ok = service == "active" and tcp
        return {"ok": ok, "service": service, "listeners": {"tcp": tcp, "udp": udp}, "port_text": str(port), "transport": "tcp+udp"}

    if protocol == "openvpn":
        port = int(item.port if item and item.port else 1194)
        transport = item.transport if item and item.transport in ("udp", "tcp") else "udp"
        service = await _service_state(conn, "openvpn-server@twinpanel")
        listen_ok = await listener(conn, port, transport)
        ok = service == "active" and listen_ok
        return {"ok": ok, "service": service, "listeners": {transport: listen_ok}, "port_text": str(port), "transport": transport}

    if protocol == "wireguard":
        port = int(item.port if item and item.port else 51820)
        service = await _service_state(conn, "wg-quick@wg-access0")
        interface_ok = bool((await cmd(conn, "wg show wg-access0", check=False)).strip())
        udp = await listener(conn, port, "udp")
        ok = service == "active" and interface_ok and udp
        return {"ok": ok, "service": service, "listeners": {"udp": udp}, "interface": interface_ok, "port_text": str(port), "transport": "udp"}

    if protocol == "l2tp":
        xl2tp = await _service_state(conn, "xl2tpd")
        ipsec = await _service_state(conn, "strongswan-starter")
        if ipsec != "active":
            ipsec = await _service_state(conn, "strongswan")
        p500 = await listener(conn, 500, "udp")
        p4500 = await listener(conn, 4500, "udp")
        p1701 = await listener(conn, 1701, "udp")
        ok = xl2tp == "active" and ipsec == "active" and p1701 and (p500 or p4500)
        return {
            "ok": ok,
            "service": f"ipsec:{ipsec}, xl2tpd:{xl2tp}",
            "listeners": {"500/udp": p500, "4500/udp": p4500, "1701/udp": p1701},
            "port_text": "500/4500/1701",
            "transport": "udp",
        }

    if protocol == "v2ray":
        port = int(item.port if item and item.port else 8443)
        service = await _service_state(conn, "xray")
        tcp = await listener(conn, port, "tcp")
        ok = service == "active" and tcp
        return {"ok": ok, "service": service, "listeners": {"tcp": tcp}, "port_text": str(port), "transport": "tcp"}

    raise HTTPException(status_code=400, detail="پروتکل نامعتبر است")


def _save_live_health(db: Session, node: Node, protocol: str, result: dict):
    item = db.query(NodeProtocolConfig).filter(
        NodeProtocolConfig.node_id == node.id,
        NodeProtocolConfig.protocol == protocol,
    ).first()
    if not item:
        item = NodeProtocolConfig(node_id=node.id, protocol=protocol)
        db.add(item)

    item.status = "online" if result["ok"] else "error"
    item.last_error = None if result["ok"] else "سرویس یا Listener در وضعیت سالم نیست"
    item.checked_at = datetime.utcnow()

    mapping = {
        "cisco": "enable_cisco",
        "openvpn": "enable_openvpn",
        "wireguard": "enable_wireguard",
        "l2tp": "enable_l2tp",
        "v2ray": "enable_v2ray",
    }
    setattr(node, mapping[protocol], bool(result["ok"]))


async def _restart_first_existing(conn, candidates: list[str]) -> str:
    checked = []
    for service in candidates:
        if not service or service in checked:
            continue
        checked.append(service)
        state = (await cmd(conn, f"systemctl show {shlex.quote(service)} -p LoadState --value", check=False)).strip()
        if state and state != "not-found":
            await cmd(conn, f"systemctl restart {shlex.quote(service)}", check=False)
            await asyncio.sleep(1)
            if await _service_state(conn, service) == "active":
                return service
    raise RuntimeError("سرویس systemd مربوط به این پروتکل پیدا نشد یا بعد از ریستارت فعال نشد")


async def _restart_protocol_service(conn, protocol: str, item: NodeProtocolConfig | None):
    saved = (item.service_name or "").strip() if item else ""
    if protocol == "cisco":
        return await _restart_first_existing(conn, [saved, "ocserv"])
    if protocol == "openvpn":
        return await _restart_first_existing(conn, [saved, "openvpn-server@twinpanel", "openvpn@twinpanel"])
    if protocol == "wireguard":
        return await _restart_first_existing(conn, [saved, "wg-quick@wg-access0"])
    if protocol == "l2tp":
        a = await _restart_first_existing(conn, ["strongswan-starter", "strongswan"])
        b = await _restart_first_existing(conn, ["xl2tpd"])
        return f"{a} + {b}"
    if protocol == "v2ray":
        return await _restart_first_existing(conn, [saved, "xray"])
    raise HTTPException(status_code=400, detail="پروتکل نامعتبر است")


@router.post("/protocol-health")
async def protocol_health(payload: ProtocolControlIn, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == payload.node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")

    conn = await ssh_connect_saved(node, db)
    try:
        stored = _protocol_settings_from_db(db, node.id)
        names = [payload.protocol] if payload.protocol else ["cisco", "openvpn", "wireguard", "l2tp", "v2ray"]
        results = {}
        for protocol in names:
            if protocol not in PROTOCOL_NAMES:
                raise HTTPException(status_code=400, detail="پروتکل نامعتبر است")
            result = await _protocol_live_health(conn, protocol, stored.get(protocol))
            result["protocol"] = protocol
            result["name"] = PROTOCOL_NAMES[protocol]
            results[protocol] = result
            _save_live_health(db, node, protocol, result)
        db.commit()
        return {"ok": all(item["ok"] for item in results.values()), "node_id": node.id, "protocols": results, "message": "بررسی سرویس‌ها انجام شد"}
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/restart-protocol")
async def restart_protocol(payload: ProtocolControlIn, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == payload.node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    if not payload.protocol or payload.protocol not in PROTOCOL_NAMES:
        raise HTTPException(status_code=400, detail="پروتکل برای ریستارت مشخص نشده است")

    conn = await ssh_connect_saved(node, db)
    try:
        stored = _protocol_settings_from_db(db, node.id)
        used_service = await _restart_protocol_service(conn, payload.protocol, stored.get(payload.protocol))
        await asyncio.sleep(2)
        result = await _protocol_live_health(conn, payload.protocol, stored.get(payload.protocol))
        result["protocol"] = payload.protocol
        result["restarted_service"] = used_service
        result["name"] = PROTOCOL_NAMES[payload.protocol]
        _save_live_health(db, node, payload.protocol, result)
        db.commit()
        return {
            "ok": result["ok"],
            "node_id": node.id,
            "protocol": result,
            "message": f"{PROTOCOL_NAMES[payload.protocol]} ریستارت شد و سالم است" if result["ok"] else f"{PROTOCOL_NAMES[payload.protocol]} ریستارت شد اما Health Check ناموفق بود",
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/repair-protocols-saved")
async def repair_protocols_saved(
    payload: RepairSavedProtocolsIn,
    request: Request,
    db: Session = Depends(get_db),
):
    node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == payload.node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")

    if node.node_type != NodeType.EXIT or node.agent_url == "local://core":
        raise HTTPException(status_code=400, detail="تعمیر پروتکل کاربری فقط برای نود خروجی مجاز است")

    stored = _protocol_settings_from_db(db, node.id)

    enabled = {
        "cisco": bool(node.enable_cisco),
        "openvpn": bool(node.enable_openvpn),
        "wireguard": bool(node.enable_wireguard),
        "l2tp": bool(node.enable_l2tp),
        "v2ray": bool(node.enable_v2ray),
    }

    def configured(name: str) -> bool:
        if not enabled.get(name, False):
            return False
        item = stored.get(name)
        if not item:
            return False
        return bool(
            item.port is not None
            or (item.port_text or "").strip()
            or (item.transport or "").strip()
            or (item.service_name or "").strip()
        )

    payload.install_cisco = configured("cisco")
    payload.install_openvpn = configured("openvpn")
    payload.install_wireguard = configured("wireguard")
    payload.install_l2tp = configured("l2tp")
    payload.install_v2ray = configured("v2ray")

    if not any((
        payload.install_cisco,
        payload.install_openvpn,
        payload.install_wireguard,
        payload.install_l2tp,
        payload.install_v2ray,
    )):
        raise HTTPException(status_code=400, detail="هیچ پروتکل نصب‌شده‌ای برای تعمیر پیدا نشد")

    if stored.get("cisco") and stored["cisco"].port:
        payload.cisco_port = stored["cisco"].port
    if stored.get("openvpn") and stored["openvpn"].port:
        payload.openvpn_port = stored["openvpn"].port
        if stored["openvpn"].transport in ("udp", "tcp"):
            payload.openvpn_transport = stored["openvpn"].transport
    if stored.get("wireguard") and stored["wireguard"].port:
        payload.wireguard_port = stored["wireguard"].port
    if stored.get("v2ray") and stored["v2ray"].port:
        payload.xray_port = stored["v2ray"].port

    conn = await ssh_connect_saved(node, db)
    try:
        await ensure_base(conn)
        results, failed, secrets_out = await provision_protocols(
            conn, payload, db, node, True
        )
        agent = await _install_or_upgrade_agent(
            conn,
            node.id,
            api_base_url(db, request),
        )
        return {
            "ok": not failed,
            "node_id": node.id,
            "protocols": results,
            "failed_protocols": failed,
            "one_time_secrets": secrets_out,
            "agent": agent,
            "message": "پروتکل‌ها بررسی و آماده شدند" if not failed else "برخی پروتکل‌ها هنوز خطا دارند",
        }
    finally:
        conn.close()
        await conn.wait_closed()


@router.post("/repair-protocols")
async def repair_protocols(
    payload: RepairProtocolsIn,
    request: Request,
    db: Session = Depends(get_db),
):
    node=db.query(Node).filter(Node.retired_at.is_(None), Node.id == payload.node_id).first()
    if not node: raise HTTPException(status_code=404,detail="سرور پیدا نشد")
    # TWINPANEL_REPAIR_EXIT_ONLY_V1
    if (
        node.node_type != NodeType.EXIT
        or node.agent_url == "local://core"
    ):
        raise HTTPException(
            status_code=400,
            detail="تعمیر پروتکل کاربری فقط برای نود خروجی مجاز است",
        )

    conn=await ssh_connect(payload)
    try:
        await ensure_base(conn)
        results,failed,secrets_out=await provision_protocols(conn,payload,db,node,True)
        agent=await _install_or_upgrade_agent(
            conn,
            node.id,
            api_base_url(db, request),
        )
        return {"ok":not failed,"node_id":node.id,"protocols":results,"failed_protocols":failed,"one_time_secrets":secrets_out,"agent":agent,"message":"پروتکل‌ها بررسی و آماده شدند" if not failed else "برخی پروتکل‌ها هنوز خطا دارند"}
    finally:
        conn.close(); await conn.wait_closed()
