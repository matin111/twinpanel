from __future__ import annotations

import asyncio
import base64
import json
import re
import shlex
import subprocess
from datetime import datetime
from pathlib import Path

from .models import NodeAccess, TunnelTransport
from .mother_access import get_value, set_value
from .ssh_relay import (
    _host_key,
    _known_host_name,
    _run,
    _write,
    relay_addresses,
    relay_interface,
    relay_number,
    relay_services,
    verify_ssh_relay,
)

MOTHER_TLS_UNIT = "twinpanel-mother-relay-tls.service"
MOTHER_TLS_PORTS = (2053, 2096, 25443, 8443)
MOTHER_DIR = Path("/etc/twinpanel/mother-relay")
MOTHER_SCRIPT = Path("/usr/local/lib/twinpanel/mother_tls_bridge.py")
MOTHER_CERT = MOTHER_DIR / "tls.crt"
MOTHER_KEY = MOTHER_DIR / "tls.key"

TLS_SERVER = r'''#!/usr/bin/env python3
import asyncio
import ssl
import sys

port = int(sys.argv[1])
cert = sys.argv[2]
key = sys.argv[3]

async def pump(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    try:
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass

async def handle(reader, writer):
    try:
        rr, rw = await asyncio.open_connection("127.0.0.1", 22)
        await asyncio.gather(pump(reader, rw), pump(rr, writer))
    except Exception as exc:
        print("MOTHER_TLS_ERROR", repr(exc), flush=True)

async def main():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert, key)
    server = await asyncio.start_server(handle, "0.0.0.0", port, ssl=ctx)
    print("MOTHER_TLS_READY", port, flush=True)
    async with server:
        await server.serve_forever()

asyncio.run(main())
'''

TLS_CLIENT = r'''#!/usr/bin/env python3
import asyncio
import ssl
import sys

remote_ip = sys.argv[1]
remote_port = int(sys.argv[2])
local_port = int(sys.argv[3])

async def pump(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    try:
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass

async def handle(reader, writer):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        rr, rw = await asyncio.open_connection(
            remote_ip,
            remote_port,
            ssl=ctx,
            server_hostname="mother.twinpanel.local",
        )
        await asyncio.gather(pump(reader, rw), pump(rr, writer))
    except Exception as exc:
        print("IRAN_TLS_ERROR", repr(exc), flush=True)

async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", local_port)
    print("IRAN_TLS_READY", local_port, flush=True)
    async with server:
        await server.serve_forever()

asyncio.run(main())
'''


def _local(command: str, *, check: bool = True, timeout: int = 120):
    result = subprocess.run(
        ["bash", "-lc", command],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        text = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        raise RuntimeError(text[-4000:] or "local_command_failed")
    return result


def _public_ipv4(value: str) -> bool:
    try:
        parts = [int(item) for item in value.strip().split(".")]
    except Exception:
        return False
    if len(parts) != 4 or any(item < 0 or item > 255 for item in parts):
        return False
    if parts[0] in {0, 10, 127}:
        return False
    if parts[0] == 169 and parts[1] == 254:
        return False
    if parts[0] == 172 and 16 <= parts[1] <= 31:
        return False
    if parts[0] == 192 and parts[1] == 168:
        return False
    return True


def mother_public_ip(db) -> str:
    configured = get_value(db, "mother.public_ip", "").strip()
    if _public_ipv4(configured):
        return configured

    result = _local(
        r'''ip -4 route get 1.1.1.1 2>/dev/null \
 | sed -n 's/.* src \([0-9.]*\).*/\1/p' \
 | head -n1''',
        check=False,
        timeout=10,
    )
    value = (result.stdout or "").strip()

    if not _public_ipv4(value):
        result = _local(
            "curl -4fsS --max-time 6 https://api.ipify.org",
            check=False,
            timeout=10,
        )
        value = (result.stdout or "").strip()

    if not _public_ipv4(value):
        raise RuntimeError("mother_public_ip_detection_failed")

    set_value(db, "mother.public_ip", value)
    db.commit()
    return value


def _local_host_key() -> str:
    for filename in (
        "/etc/ssh/ssh_host_ed25519_key.pub",
        "/etc/ssh/ssh_host_ecdsa_key.pub",
        "/etc/ssh/ssh_host_rsa_key.pub",
    ):
        path = Path(filename)
        if not path.is_file():
            continue
        parts = path.read_text().strip().split()
        if len(parts) >= 2:
            return f"{parts[0]} {parts[1]}"
    raise RuntimeError("mother_ssh_host_key_missing")


def _port_busy(port: int) -> bool:
    result = _local(
        f"ss -lntH | grep -Eq '[:.]{int(port)}[[:space:]]'",
        check=False,
        timeout=10,
    )
    return result.returncode == 0


def ensure_mother_tls_service(db) -> tuple[str, int]:
    mother_ip = mother_public_ip(db)
    try:
        configured = int(get_value(db, "mother.relay_tls_port", "2053"))
    except Exception:
        configured = 2053

    active = (
        _local(
            f"systemctl is-active --quiet {MOTHER_TLS_UNIT}",
            check=False,
            timeout=10,
        ).returncode == 0
    )

    candidates: list[int] = []
    for port in (configured, *MOTHER_TLS_PORTS):
        if 1024 <= int(port) <= 65535 and int(port) not in candidates:
            candidates.append(int(port))

    selected = None
    for port in candidates:
        if active and port == configured:
            selected = port
            break
        if not _port_busy(port):
            selected = port
            break

    if selected is None:
        raise RuntimeError("mother_relay_no_free_tls_port")

    MOTHER_DIR.mkdir(parents=True, exist_ok=True)
    MOTHER_SCRIPT.parent.mkdir(parents=True, exist_ok=True)
    MOTHER_SCRIPT.write_text(TLS_SERVER)
    MOTHER_SCRIPT.chmod(0o755)

    if not MOTHER_CERT.is_file() or not MOTHER_KEY.is_file():
        _local(
            f'''set -e
openssl req \
 -x509 \
 -newkey rsa:2048 \
 -nodes \
 -sha256 \
 -days 825 \
 -subj '/CN=mother.twinpanel.local' \
 -keyout {shlex.quote(str(MOTHER_KEY))} \
 -out {shlex.quote(str(MOTHER_CERT))} \
 >/dev/null 2>&1
chmod 600 {shlex.quote(str(MOTHER_KEY))}
chmod 644 {shlex.quote(str(MOTHER_CERT))}'''
        )

    unit = f'''[Unit]
Description=TwinPanel Mother Relay TLS
After=network-online.target ssh.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {MOTHER_SCRIPT} {selected} {MOTHER_CERT} {MOTHER_KEY}
Restart=always
RestartSec=2
LimitNOFILE=1048576
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
'''
    Path(f"/etc/systemd/system/{MOTHER_TLS_UNIT}").write_text(unit)

    _local(
        f'''set -e
systemctl daemon-reload
systemctl enable {MOTHER_TLS_UNIT} >/dev/null
systemctl restart {MOTHER_TLS_UNIT}
for i in $(seq 1 15); do
    if systemctl is-active --quiet {MOTHER_TLS_UNIT} \
       && ss -lntH | grep -Eq '[:.]{selected}[[:space:]]'; then
        exit 0
    fi
    sleep 1
done
systemctl status {MOTHER_TLS_UNIT} --no-pager -l || true
journalctl -u {MOTHER_TLS_UNIT} -n 80 --no-pager || true
exit 70''',
        timeout=30,
    )

    set_value(db, "mother.relay_tls_port", str(selected))
    db.commit()
    return mother_ip, selected


def _allow_iran(mother_port: int, iran_ip: str) -> None:
    chain = f"TPMR{int(mother_port)}"
    _local(
        f'''set -e
if command -v iptables >/dev/null 2>&1; then
    iptables -N {chain} 2>/dev/null || true
    iptables -C INPUT -p tcp --dport {int(mother_port)} -j {chain} 2>/dev/null || \
      iptables -I INPUT -p tcp --dport {int(mother_port)} -j {chain}
    iptables -C {chain} -s {shlex.quote(iran_ip)} -j ACCEPT 2>/dev/null || \
      iptables -I {chain} 1 -s {shlex.quote(iran_ip)} -j ACCEPT
    iptables -C {chain} -j DROP 2>/dev/null || \
      iptables -A {chain} -j DROP
fi'''
    )


def _authorize_panel_key(*, public_key: str, exit_ip: str, exit_port: int, tag: str) -> None:
    line = (
        'from="127.0.0.1",no-agent-forwarding,no-X11-forwarding,'
        f'no-pty,no-user-rc,permitopen="{exit_ip}:{int(exit_port)}" '
        f"{public_key} {tag}"
    )
    encoded = base64.b64encode(line.encode()).decode()
    _local(
        f'''set -e
install -d -m 700 /root/.ssh
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
grep -v {shlex.quote(tag + '$')} /root/.ssh/authorized_keys \
  >/root/.ssh/authorized_keys.tp-mother.tmp || true
printf '%s' {shlex.quote(encoded)} | base64 -d \
  >>/root/.ssh/authorized_keys.tp-mother.tmp
printf '\n' >>/root/.ssh/authorized_keys.tp-mother.tmp
mv /root/.ssh/authorized_keys.tp-mother.tmp /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys'''
    )


async def _local_tls_port(conn, tunnel_id: int, service: str) -> int:
    await _run(
        conn,
        f"systemctl stop {shlex.quote(service)} >/dev/null 2>&1 || true",
        check=False,
    )
    base = 32000 + (int(tunnel_id) % 20000)
    for offset in (0, 1000, 2000, 3000, 4000, 5000, 6000):
        port = base + offset
        if port > 65000:
            port = 32000 + (port % 10000)
        result = await _run(
            conn,
            f"ss -lntH | grep -Eq '[:.]{port}[[:space:]]'",
            check=False,
            timeout=10,
        )
        if result.exit_status != 0:
            return port
    raise RuntimeError("iran_local_tls_port_exhausted")


def _received_count(text: str) -> tuple[int, int]:
    match = re.search(
        r"(\d+)\s+packets transmitted,\s+(\d+)\s+(?:packets )?received",
        text,
    )
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


async def provision_mother_ssh_relay(tunnel, iran, exit_node, db) -> dict:
    from .routers.provision import ssh_connect_saved

    tid = int(tunnel.id)
    number = relay_number(tunnel)
    iface = relay_interface(tunnel)
    network, iran_ip, exit_ip = relay_addresses(tunnel)
    iran_service, iran_helper_service, exit_helper_service = relay_services(tunnel)
    tls_service = f"tp{tid}-relay-tls.service"
    base = f"/etc/twinpanel/ssh-relay/tunnel-{tid}"
    tag_hop = f"tp{tid}-mother-hop"
    tag_exit = f"tp{tid}-mother-exit"

    iran_access = db.query(NodeAccess).filter(NodeAccess.node_id == int(iran.id)).first()
    exit_access = db.query(NodeAccess).filter(NodeAccess.node_id == int(exit_node.id)).first()

    if not iran_access or str(iran_access.ssh_username or "root") != "root":
        raise RuntimeError("mother_relay_requires_root_iran_access")
    if not exit_access or str(exit_access.ssh_username or "root") != "root":
        raise RuntimeError("mother_relay_requires_root_exit_access")

    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == tid,
            TunnelTransport.transport == "ssh_relay",
        )
        .first()
    )
    if not row:
        row = TunnelTransport(
            tunnel_id=tid,
            transport="ssh_relay",
            priority=300,
            enabled=False,
            status="provisioning",
        )
        db.add(row)
    else:
        row.priority = 300
        row.enabled = False
        row.status = "provisioning"
        row.last_error = None
        row.updated_at = datetime.utcnow()
    db.commit()

    ci = None
    ce = None

    try:
        mother_ip, mother_tls_port = ensure_mother_tls_service(db)
        _allow_iran(mother_tls_port, str(iran.public_ip))

        ci = await ssh_connect_saved(iran, db)
        ce = await ssh_connect_saved(exit_node, db)

        await _run(
            ci,
            f'''set -e
install -d -m 700 {shlex.quote(base)}
if [ ! -s {shlex.quote(base + '/id_ed25519')} ]; then
    ssh-keygen -q -t ed25519 -N '' -f {shlex.quote(base + '/id_ed25519')}
fi
chmod 600 {shlex.quote(base + '/id_ed25519')}
chmod 644 {shlex.quote(base + '/id_ed25519.pub')}''',
        )

        public_key = (
            await _run(ci, f"cat {shlex.quote(base + '/id_ed25519.pub')}")
        ).stdout.strip()
        if not public_key.startswith("ssh-ed25519 "):
            raise RuntimeError("mother_relay_invalid_public_key")

        _authorize_panel_key(
            public_key=public_key,
            exit_ip=str(exit_node.public_ip),
            exit_port=int(exit_access.ssh_port),
            tag=tag_hop,
        )

        exit_line = (
            f'from="{mother_ip}",no-agent-forwarding,no-X11-forwarding,'
            f'no-pty,no-user-rc,no-port-forwarding,tunnel="{number}" '
            f"{public_key} {tag_exit}"
        )
        exit_encoded = base64.b64encode(exit_line.encode()).decode()

        await _run(
            ce,
            f'''set -e
install -d -m 700 /root/.ssh
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
grep -v {shlex.quote(tag_exit + '$')} /root/.ssh/authorized_keys \
  >/root/.ssh/authorized_keys.tp-mother.tmp || true
printf '%s' {shlex.quote(exit_encoded)} | base64 -d \
  >>/root/.ssh/authorized_keys.tp-mother.tmp
printf '\n' >>/root/.ssh/authorized_keys.tp-mother.tmp
mv /root/.ssh/authorized_keys.tp-mother.tmp /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys''',
        )

        marker_begin = f"# BEGIN TWINPANEL MOTHER RELAY {tid}"
        marker_end = f"# END TWINPANEL MOTHER RELAY {tid}"
        policy = (
            marker_begin + "\n"
            + f"Match User root Address {mother_ip}\n"
            + "    PermitTunnel point-to-point\n"
            + "Match all\n"
            + marker_end + "\n"
        )
        policy_encoded = base64.b64encode(policy.encode()).decode()

        await _run(
            ce,
            f'''set -e
cp -a /etc/ssh/sshd_config \
 /etc/ssh/sshd_config.bak-tp-mother-$(date +%Y%m%d-%H%M%S)
python3 - <<'PY2'
from pathlib import Path
import base64
p=Path('/etc/ssh/sshd_config')
s=p.read_text()
begin={marker_begin!r}
end={marker_end!r}
while begin in s and end in s:
    a=s.index(begin)
    b=s.index(end,a)+len(end)
    s=s[:a]+s[b:]
block=base64.b64decode({policy_encoded!r}).decode()
p.write_text(s.rstrip()+"\\n\\n"+block)
PY2
sshd -t
VALUE="$(sshd -T -C user=root,addr={mother_ip},host=tp{tid}-exit \
 | sed -n 's/^permittunnel //p' | head -n1)"
[ "$VALUE" = "point-to-point" ] || [ "$VALUE" = "yes" ]
systemctl reload ssh 2>/dev/null || systemctl reload sshd''',
        )

        mother_key = _local_host_key()
        exit_key = await _host_key(ce)
        local_port = await _local_tls_port(ci, tid, tls_service)

        tls_client_path = f"/usr/local/lib/twinpanel/tp{tid}_mother_tls_client.py"
        await _write(ci, tls_client_path, TLS_CLIENT, "700")

        tls_unit = f'''[Unit]
Description=TwinPanel Tunnel {tid} Mother TLS Carrier
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {tls_client_path} {mother_ip} {mother_tls_port} {local_port}
Restart=always
RestartSec=2
LimitNOFILE=1048576
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
'''
        await _write(ci, f"/etc/systemd/system/{tls_service}", tls_unit, "644")

        known_hosts = (
            f"[127.0.0.1]:{local_port} {mother_key}\n"
            + _known_host_name(str(exit_node.public_ip), int(exit_access.ssh_port))
            + " " + exit_key + "\n"
        )
        await _write(ci, base + "/known_hosts", known_hosts, "600")

        ssh_config = f'''Host tp{tid}-hop
    HostName 127.0.0.1
    Port {local_port}
    User root
    IdentityFile {base}/id_ed25519
    IdentitiesOnly yes
    BatchMode yes
    PasswordAuthentication no
    StrictHostKeyChecking yes
    UserKnownHostsFile {base}/known_hosts
    ConnectTimeout 10
    ServerAliveInterval 5
    ServerAliveCountMax 3
    RequestTTY no

Host tp{tid}-exit
    HostName {exit_node.public_ip}
    Port {int(exit_access.ssh_port)}
    User root
    IdentityFile {base}/id_ed25519
    IdentitiesOnly yes
    BatchMode yes
    PasswordAuthentication no
    StrictHostKeyChecking yes
    UserKnownHostsFile {base}/known_hosts
    ProxyJump tp{tid}-hop
    ConnectTimeout 10
    ServerAliveInterval 5
    ServerAliveCountMax 3
    ExitOnForwardFailure yes
    Tunnel point-to-point
    TunnelDevice {number}:{number}
    RequestTTY no
'''
        await _write(ci, base + "/ssh_config", ssh_config, "600")

        iran_helper_path = f"/usr/local/sbin/tp{tid}-relay-iran-if"
        exit_helper_path = f"/usr/local/sbin/tp{tid}-relay-exit-if"

        iran_helper = f'''#!/bin/bash
set -u
while true; do
  if ip link show {iface} >/dev/null 2>&1; then
    ip link set dev {iface} mtu 1280 up >/dev/null 2>&1 || true
    ip addr replace {iran_ip} peer {exit_ip} dev {iface} >/dev/null 2>&1 || true
  fi
  sleep 1
done
'''
        exit_helper = f'''#!/bin/bash
set -u
while true; do
  if ip link show {iface} >/dev/null 2>&1; then
    ip link set dev {iface} mtu 1280 up >/dev/null 2>&1 || true
    ip addr replace {exit_ip} peer {iran_ip} dev {iface} >/dev/null 2>&1 || true
  fi
  sleep 1
done
'''

        await _write(ci, iran_helper_path, iran_helper, "700")
        await _write(ce, exit_helper_path, exit_helper, "700")

        iran_helper_unit = f'''[Unit]
Description=TwinPanel Tunnel {tid} Mother Relay Iran Interface
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={iran_helper_path}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
'''
        exit_helper_unit = f'''[Unit]
Description=TwinPanel Tunnel {tid} Mother Relay Exit Interface
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={exit_helper_path}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
'''
        ssh_unit = f'''[Unit]
Description=TwinPanel Tunnel {tid} SSH Relay via Mother {mother_ip}
After=network-online.target {tls_service} {iran_helper_service}
Wants=network-online.target {tls_service} {iran_helper_service}

[Service]
Type=simple
ExecStart=/usr/bin/ssh -F {base}/ssh_config -N tp{tid}-exit
Restart=always
RestartSec=2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
'''

        await _write(ci, f"/etc/systemd/system/{iran_helper_service}", iran_helper_unit, "644")
        await _write(ce, f"/etc/systemd/system/{exit_helper_service}", exit_helper_unit, "644")
        await _write(ci, f"/etc/systemd/system/{iran_service}", ssh_unit, "644")

        await _run(
            ce,
            f"systemctl daemon-reload; systemctl enable --now {shlex.quote(exit_helper_service)} >/dev/null",
        )
        await _run(
            ci,
            f'''set -e
systemctl daemon-reload
systemctl enable --now {shlex.quote(tls_service)} >/dev/null
systemctl enable --now {shlex.quote(iran_helper_service)} >/dev/null
systemctl enable {shlex.quote(iran_service)} >/dev/null
systemctl restart {shlex.quote(iran_service)}''',
        )

        ready = False
        for _ in range(35):
            result = await _run(
                ci,
                f'''systemctl is-active --quiet {shlex.quote(tls_service)} &&
systemctl is-active --quiet {shlex.quote(iran_service)} &&
ip addr show {shlex.quote(iface)} 2>/dev/null | grep -q {shlex.quote(iran_ip)} &&
ping -I {shlex.quote(iface)} -c 1 -W 2 {shlex.quote(exit_ip)} >/dev/null 2>&1''',
                check=False,
                timeout=10,
            )
            if result.exit_status == 0:
                ready = True
                break
            await asyncio.sleep(1)

        if not ready:
            diag = await _run(
                ci,
                f'''systemctl status {shlex.quote(tls_service)} --no-pager -l || true
systemctl status {shlex.quote(iran_service)} --no-pager -l || true
journalctl -u {shlex.quote(tls_service)} -n 60 --no-pager || true
journalctl -u {shlex.quote(iran_service)} -n 60 --no-pager || true''',
                check=False,
                timeout=20,
            )
            raise RuntimeError("mother_relay_not_ready: " + (diag.stdout or "")[-2500:])

        sustained = await _run(
            ci,
            f"LC_ALL=C ping -I {shlex.quote(iface)} -c 20 -i 0.20 -W 2 -s 1000 {shlex.quote(exit_ip)}",
            check=False,
            timeout=45,
        )
        ping_text = (sustained.stdout or "") + "\n" + (sustained.stderr or "")
        sent, received = _received_count(ping_text)

        if sent < 1 or received * 100 < sent * 90:
            raise RuntimeError("mother_relay_ping_quality_failed: " + ping_text[-1800:])

        quality = "online" if received == sent else "degraded"
        cfg = {
            "type": "ssh_relay",
            "carrier": "mother_tls",
            "quality": quality,
            "mother_public_ip": mother_ip,
            "mother_tls_port": mother_tls_port,
            "local_tls_port": local_port,
            "tls_service": tls_service,
            "exit_node_id": int(exit_node.id),
            "network": network,
            "interface": iface,
            "iran_ip": iran_ip,
            "exit_ip": exit_ip,
            "iran_service": iran_service,
            "iran_helper": iran_helper_service,
            "exit_helper": exit_helper_service,
            "route_selectable": True,
            "ping_probe": f"{received}/{sent}",
        }

        row = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == tid,
                TunnelTransport.transport == "ssh_relay",
            )
            .first()
        )
        if not row:
            row = TunnelTransport(tunnel_id=tid, transport="ssh_relay", priority=300)
            db.add(row)

        row.priority = 300
        row.enabled = True
        row.status = "online"
        row.last_error = None if quality == "online" else f"quality_degraded: ping={received}/{sent}"
        row.last_healthy_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
        row.config_text = json.dumps(cfg, ensure_ascii=False)
        db.commit()

        health = await verify_ssh_relay(tunnel, iran, db)
        return {
            **health,
            "carrier": "mother_tls",
            "quality": quality,
            "ping_probe": f"{received}/{sent}",
            "mother_public_ip": mother_ip,
            "mother_tls_port": mother_tls_port,
        }

    except Exception as exc:
        db.rollback()
        row = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id == tid,
                TunnelTransport.transport == "ssh_relay",
            )
            .first()
        )
        if not row:
            row = TunnelTransport(tunnel_id=tid, transport="ssh_relay", priority=300)
            db.add(row)
        row.enabled = False
        row.status = "offline"
        row.last_error = str(exc)[:700]
        row.updated_at = datetime.utcnow()
        db.commit()

        if ci:
            await _run(
                ci,
                f"systemctl disable --now {shlex.quote(iran_service)} {shlex.quote(iran_helper_service)} {shlex.quote(tls_service)} >/dev/null 2>&1 || true; ip link del {shlex.quote(iface)} >/dev/null 2>&1 || true",
                check=False,
            )
        if ce:
            await _run(
                ce,
                f"systemctl disable --now {shlex.quote(exit_helper_service)} >/dev/null 2>&1 || true; ip link del {shlex.quote(iface)} >/dev/null 2>&1 || true",
                check=False,
            )
        raise
    finally:
        for conn in (ci, ce):
            if conn:
                conn.close()
                await conn.wait_closed()
