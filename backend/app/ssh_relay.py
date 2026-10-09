# TWINPANEL_GENERIC_SSH_RELAY_V61
from __future__ import annotations

import asyncio
import base64
import json
import os
import shlex
from datetime import datetime
from pathlib import Path

from .models import Node, NodeAccess, NodeStatus, NodeType, TunnelTransport


def relay_number(tunnel) -> int:
    return 100 + int(tunnel.id)


def relay_interface(tunnel) -> str:
    return f"tun{relay_number(tunnel)}"[:15]


def relay_services(tunnel) -> tuple[str, str, str]:
    tid = int(tunnel.id)
    return (
        f"tp{tid}-relay-ssh.service",
        f"tp{tid}-relay-if.service",
        f"tp{tid}-relay-exit-if.service",
    )


def relay_addresses(tunnel) -> tuple[str, str, str]:
    tid = int(tunnel.id)
    block = max(0, (tid - 1) // 250)
    oct2 = 80 + block
    if oct2 > 199:
        raise RuntimeError("relay address pool exhausted")
    oct3 = ((tid - 1) % 250) + 1
    iran = f"10.{oct2}.{oct3}.1"
    exit_ip = f"10.{oct2}.{oct3}.2"
    return f"10.{oct2}.{oct3}.0/30", iran, exit_ip


def _member(db, tunnel_id: int):
    return (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == "ssh_relay",
        )
        .first()
    )


def relay_config(db, tunnel) -> dict:
    row = _member(db, int(tunnel.id))
    if not row or not row.config_text:
        return {}
    try:
        value = json.loads(row.config_text)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def relay_desired_meta(db, tunnel, node_id: int) -> dict | None:
    cfg = relay_config(db, tunnel)
    if not cfg:
        return None

    iface = str(cfg.get("interface") or relay_interface(tunnel))
    iran_ip = str(cfg.get("iran_ip") or "").strip()
    exit_ip = str(cfg.get("exit_ip") or "").strip()
    if not iran_ip or not exit_ip:
        _, iran_ip, exit_ip = relay_addresses(tunnel)

    iran_service, _, exit_helper = relay_services(tunnel)
    iran_service = str(cfg.get("iran_service") or iran_service)
    exit_helper = str(cfg.get("exit_helper") or exit_helper)

    is_iran = int(node_id) == int(tunnel.iran_node_id)
    is_exit = int(node_id) == int(tunnel.exit_node_id)
    if not (is_iran or is_exit):
        return None

    return {
        "interface": iface,
        "network": str(cfg.get("network") or relay_addresses(tunnel)[0]),
        "local_address": f"{iran_ip}/30" if is_iran else f"{exit_ip}/30",
        "peer_tunnel_ip": exit_ip if is_iran else iran_ip,
        "exit_tunnel_ip": exit_ip,
        "health_interface": iface,
        "health_peer_tunnel_ip": exit_ip if is_iran else iran_ip,
        "health_service": iran_service if is_iran else exit_helper,
    }


def choose_relay_node(db, tunnel):
    cfg = relay_config(db, tunnel)
    configured_id = cfg.get("relay_node_id")

    rows = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.node_type == NodeType.EXIT,
            Node.status == NodeStatus.ONLINE,
            Node.id != int(tunnel.exit_node_id),
        )
        .order_by(Node.id.asc())
        .all()
    )

    target = db.get(Node, int(tunnel.exit_node_id))
    target_ip = str(target.public_ip or "").strip() if target else ""

    def usable(node) -> bool:
        if not node:
            return False
        if str(node.public_ip or "").strip() == target_ip:
            return False
        access = (
            db.query(NodeAccess)
            .filter(NodeAccess.node_id == int(node.id))
            .first()
        )
        return bool(
            access
            and access.private_key_path
            and Path(access.private_key_path).exists()
        )

    if configured_id:
        configured = db.get(Node, int(configured_id))
        if configured in rows and usable(configured):
            return configured

    for node in rows:
        if usable(node):
            return node
    return None


async def _run(conn, command: str, *, check: bool = True, timeout: int = 120):
    result = await conn.run(command, check=False, timeout=timeout)
    if check and result.exit_status != 0:
        raise RuntimeError(
            (result.stderr or result.stdout or "remote command failed")[-3000:]
        )
    return result


async def _write(conn, path: str, content: str, mode: str = "600"):
    encoded = base64.b64encode(content.encode()).decode()
    parent = str(Path(path).parent)
    await _run(
        conn,
        f"""
set -e
install -d -m 700 {shlex.quote(parent)}
printf '%s' {shlex.quote(encoded)} | base64 -d > {shlex.quote(path)}
chmod {shlex.quote(mode)} {shlex.quote(path)}
""",
    )


async def _host_key(conn) -> str:
    result = await _run(
        conn,
        r"""
set -e
for f in /etc/ssh/ssh_host_ed25519_key.pub /etc/ssh/ssh_host_ecdsa_key.pub /etc/ssh/ssh_host_rsa_key.pub; do
    if [ -s "$f" ]; then
        awk '{print $1" "$2}' "$f"
        exit 0
    fi
done
exit 44
""",
    )
    value = result.stdout.strip()
    if not value:
        raise RuntimeError("ssh host key missing")
    return value


def _known_host_name(host: str, port: int) -> str:
    return host if int(port) == 22 else f"[{host}]:{int(port)}"


async def verify_ssh_relay(tunnel, iran, db) -> dict:
    from .routers.provision import ssh_connect_saved

    cfg = relay_config(db, tunnel)
    _, iran_ip_default, exit_ip_default = relay_addresses(tunnel)
    iface = str(cfg.get("interface") or relay_interface(tunnel))
    iran_ip = str(cfg.get("iran_ip") or iran_ip_default)
    exit_ip = str(cfg.get("exit_ip") or exit_ip_default)
    iran_service = str(
        cfg.get("iran_service") or relay_services(tunnel)[0]
    )

    conn = await ssh_connect_saved(iran, db)
    try:
        result = await _run(
            conn,
            f"""
set -e
systemctl is-active --quiet {shlex.quote(iran_service)}
ip addr show {shlex.quote(iface)} | grep -q {shlex.quote(iran_ip)}
LC_ALL=C ping -I {shlex.quote(iface)} -c 5 -i 0.20 -W 2 -s 900 {shlex.quote(exit_ip)}
""",
            check=False,
            timeout=25,
        )
        if result.exit_status != 0:
            raise RuntimeError(
                (result.stderr or result.stdout or "relay health failed")[-1800:]
            )

        latency = None
        for line in result.stdout.splitlines():
            if "min/avg/max" in line and "=" in line:
                try:
                    latency = int(float(line.split("=", 1)[1].strip().split("/")[1]))
                except Exception:
                    pass
        return {
            "ok": True,
            "interface": iface,
            "iran_ip": iran_ip,
            "exit_ip": exit_ip,
            "latency_ms": latency,
        }
    finally:
        conn.close()
        await conn.wait_closed()


async def _udp_probe(ci, ce, tunnel, iran_ip: str, exit_ip: str):
    tid = int(tunnel.id)
    port = 40000 + (tid % 2000)
    server_path = f"/tmp/tp-relay-{tid}-udp-server.py"
    client_path = f"/tmp/tp-relay-{tid}-udp-client.py"
    unit = f"tp-relay-{tid}-udp-test.service"

    server = f'''import socket\ns=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)\ns.bind(({exit_ip!r},{port}))\ns.settimeout(35)\ncount=0\nwhile count<20:\n data,addr=s.recvfrom(65535)\n s.sendto(data,addr)\n count+=1\nprint("COUNT="+str(count),flush=True)\ns.close()\n'''
    client = f'''import socket,time\ns=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)\ns.bind(({iran_ip!r},0))\ns.settimeout(2)\nok=0\nfor seq in range(1,21):\n p=("TPR-%04d-"%seq).encode()+b"R"*900\n try:\n  s.sendto(p,({exit_ip!r},{port}))\n  d,_=s.recvfrom(65535)\n  if d==p: ok+=1\n except Exception: pass\n time.sleep(.15)\nprint("PASS="+str(ok),flush=True)\nif ok!=20: raise SystemExit(50)\n'''

    await _write(ce, server_path, server, "600")
    await _write(ci, client_path, client, "600")
    try:
        await _run(
            ce,
            f"""
systemctl stop {shlex.quote(unit)} >/dev/null 2>&1 || true
systemd-run --unit={shlex.quote(unit[:-8])} --property=Restart=no python3 -u {shlex.quote(server_path)}
""",
        )
        await asyncio.sleep(1)
        result = await _run(
            ci,
            f"python3 {shlex.quote(client_path)}",
            check=False,
            timeout=65,
        )
        if result.exit_status != 0 or "PASS=20" not in result.stdout:
            raise RuntimeError(
                "relay UDP probe failed: "
                + (result.stderr or result.stdout or "unknown")[-1200:]
            )
    finally:
        await _run(
            ce,
            f"systemctl stop {shlex.quote(unit)} >/dev/null 2>&1 || true; rm -f {shlex.quote(server_path)}",
            check=False,
        )
        await _run(ci, f"rm -f {shlex.quote(client_path)}", check=False)


async def provision_ssh_relay(tunnel, iran, relay, exit_node, db) -> dict:
    from .routers.provision import ssh_connect_saved

    for node in (iran, relay, exit_node):
        access = (
            db.query(NodeAccess)
            .filter(NodeAccess.node_id == int(node.id))
            .first()
        )
        if not access or str(access.ssh_username or "root") != "root":
            raise RuntimeError(
                f"SSH Relay requires saved root access on node {node.id}"
            )

    relay_access = (
        db.query(NodeAccess).filter(NodeAccess.node_id == int(relay.id)).first()
    )
    exit_access = (
        db.query(NodeAccess).filter(NodeAccess.node_id == int(exit_node.id)).first()
    )

    tid = int(tunnel.id)
    number = relay_number(tunnel)
    iface = relay_interface(tunnel)
    network, iran_ip, exit_ip = relay_addresses(tunnel)
    iran_service, iran_helper_service, exit_helper_service = relay_services(tunnel)
    base = f"/etc/twinpanel/ssh-relay/tunnel-{tid}"
    tag_hop = f"tp{tid}-relay-hop"
    tag_exit = f"tp{tid}-relay-exit"

    ci = cr = ce = None
    row = _member(db, tid)
    if not row:
        row = TunnelTransport(
            tunnel_id=tid,
            transport="ssh_relay",
            priority=200,
            enabled=False,
            status="provisioning",
        )
        db.add(row)
        db.flush()
    else:
        row.enabled = False
        row.status = "provisioning"
        row.last_error = None
        row.updated_at = datetime.utcnow()
    db.commit()

    try:
        ci = await ssh_connect_saved(iran, db)
        cr = await ssh_connect_saved(relay, db)
        ce = await ssh_connect_saved(exit_node, db)

        await _run(
            ci,
            f"""
set -e
install -d -m 700 {shlex.quote(base)}
if [ ! -s {shlex.quote(base + '/id_ed25519')} ]; then
  ssh-keygen -q -t ed25519 -N '' -f {shlex.quote(base + '/id_ed25519')}
fi
chmod 600 {shlex.quote(base + '/id_ed25519')}
chmod 644 {shlex.quote(base + '/id_ed25519.pub')}
""",
        )
        pub = (await _run(ci, f"cat {shlex.quote(base + '/id_ed25519.pub')}")).stdout.strip()
        if not pub.startswith("ssh-ed25519 "):
            raise RuntimeError("invalid relay public key")

        relay_line = (
            f'from="{iran.public_ip}",no-agent-forwarding,no-X11-forwarding,'
            f'no-pty,no-user-rc,permitopen="{exit_node.public_ip}:{int(exit_access.ssh_port)}" '
            f'{pub} {tag_hop}'
        )
        exit_line = (
            f'from="{relay.public_ip}",no-agent-forwarding,no-X11-forwarding,'
            f'no-pty,no-user-rc,no-port-forwarding,tunnel="{number}" '
            f'{pub} {tag_exit}'
        )

        for conn, line, tag in ((cr, relay_line, tag_hop), (ce, exit_line, tag_exit)):
            encoded = base64.b64encode(line.encode()).decode()
            await _run(
                conn,
                f"""
set -e
install -d -m 700 /root/.ssh
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
cp -a /root/.ssh/authorized_keys /root/.ssh/authorized_keys.bak-tp-relay-$(date +%Y%m%d-%H%M%S)
grep -v {shlex.quote(tag + '$')} /root/.ssh/authorized_keys > /root/.ssh/authorized_keys.tmp || true
printf '%s' {shlex.quote(encoded)} | base64 -d >> /root/.ssh/authorized_keys.tmp
printf '\n' >> /root/.ssh/authorized_keys.tmp
mv /root/.ssh/authorized_keys.tmp /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
""",
            )

        marker_begin = f"# BEGIN TWINPANEL RELAY {tid}"
        marker_end = f"# END TWINPANEL RELAY {tid}"
        policy = (
            marker_begin + "\n"
            f"Match User root Address {relay.public_ip}\n"
            "    PermitTunnel point-to-point\n"
            "Match all\n"
            + marker_end + "\n"
        )
        encoded_policy = base64.b64encode(policy.encode()).decode()
        await _run(
            ce,
            f"""
set -e
cp -a /etc/ssh/sshd_config /etc/ssh/sshd_config.bak-tp-relay-$(date +%Y%m%d-%H%M%S)
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
block=base64.b64decode({encoded_policy!r}).decode()
p.write_text(s.rstrip()+"\\n\\n"+block)
PY2
sshd -t
VALUE=$(sshd -T -C user=root,addr={shlex.quote(str(relay.public_ip))},host=tp{tid}-exit | awk '/^permittunnel / {{print $2}}')
[ "$VALUE" = "point-to-point" ] || [ "$VALUE" = "yes" ]
systemctl reload ssh 2>/dev/null || systemctl reload sshd
""",
        )

        relay_key = await _host_key(cr)
        exit_key = await _host_key(ce)
        known_hosts = (
            f"{_known_host_name(str(relay.public_ip), int(relay_access.ssh_port))} {relay_key}\n"
            f"{_known_host_name(str(exit_node.public_ip), int(exit_access.ssh_port))} {exit_key}\n"
        )
        await _write(ci, base + "/known_hosts", known_hosts, "600")

        ssh_cfg = f"""Host tp{tid}-hop
    HostName {relay.public_ip}
    Port {int(relay_access.ssh_port)}
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
"""
        await _write(ci, base + "/ssh_config", ssh_cfg, "600")

        iran_helper_path = f"/usr/local/sbin/tp{tid}-relay-iran-if"
        exit_helper_path = f"/usr/local/sbin/tp{tid}-relay-exit-if"
        iran_helper = f"""#!/bin/bash
set -u
while true; do
  if ip link show {iface} >/dev/null 2>&1; then
    ip link set dev {iface} mtu 1280 up >/dev/null 2>&1 || true
    ip addr replace {iran_ip} peer {exit_ip} dev {iface} >/dev/null 2>&1 || true
  fi
  sleep 1
done
"""
        exit_helper = f"""#!/bin/bash
set -u
while true; do
  if ip link show {iface} >/dev/null 2>&1; then
    ip link set dev {iface} mtu 1280 up >/dev/null 2>&1 || true
    ip addr replace {exit_ip} peer {iran_ip} dev {iface} >/dev/null 2>&1 || true
  fi
  sleep 1
done
"""
        await _write(ci, iran_helper_path, iran_helper, "700")
        await _write(ce, exit_helper_path, exit_helper, "700")

        iran_helper_unit = f"""[Unit]
Description=TwinPanel Tunnel {tid} Relay Iran Interface
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={iran_helper_path}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
"""
        exit_helper_unit = f"""[Unit]
Description=TwinPanel Tunnel {tid} Relay Exit Interface
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={exit_helper_path}
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
"""
        ssh_unit = f"""[Unit]
Description=TwinPanel Tunnel {tid} SSH Relay via Node {int(relay.id)}
After=network-online.target {iran_helper_service}
Wants=network-online.target {iran_helper_service}

[Service]
Type=simple
ExecStart=/usr/bin/ssh -F {base}/ssh_config -N tp{tid}-exit
Restart=always
RestartSec=2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
        await _write(ci, f"/etc/systemd/system/{iran_helper_service}", iran_helper_unit, "644")
        await _write(ce, f"/etc/systemd/system/{exit_helper_service}", exit_helper_unit, "644")
        await _write(ci, f"/etc/systemd/system/{iran_service}", ssh_unit, "644")

        await _run(
            ce,
            f"systemctl daemon-reload; systemctl enable --now {shlex.quote(exit_helper_service)} >/dev/null",
        )
        await _run(
            ci,
            f"systemctl daemon-reload; systemctl enable --now {shlex.quote(iran_helper_service)} >/dev/null; systemctl enable {shlex.quote(iran_service)} >/dev/null; systemctl restart {shlex.quote(iran_service)}",
        )

        ready = False
        for _ in range(30):
            probe = await _run(
                ci,
                f"systemctl is-active --quiet {shlex.quote(iran_service)} && ip addr show {shlex.quote(iface)} 2>/dev/null | grep -q {shlex.quote(iran_ip)} && ping -I {shlex.quote(iface)} -c 1 -W 1 {shlex.quote(exit_ip)} >/dev/null 2>&1",
                check=False,
                timeout=8,
            )
            if probe.exit_status == 0:
                ready = True
                break
            await asyncio.sleep(1)
        if not ready:
            raise RuntimeError("ssh relay interface did not become ready")

        sustained = await _run(
            ci,
            f"LC_ALL=C ping -I {shlex.quote(iface)} -c 20 -i 0.20 -W 2 -s 1000 {shlex.quote(exit_ip)}",
            check=False,
            timeout=45,
        )
        if sustained.exit_status != 0 or "0% packet loss" not in sustained.stdout:
            raise RuntimeError("ssh relay sustained ping failed: " + sustained.stdout[-1600:])

        await _udp_probe(ci, ce, tunnel, iran_ip, exit_ip)

        cfg = {
            "type": "ssh_relay",
            "relay_node_id": int(relay.id),
            "relay_public_ip": str(relay.public_ip),
            "exit_node_id": int(exit_node.id),
            "network": network,
            "interface": iface,
            "iran_ip": iran_ip,
            "exit_ip": exit_ip,
            "iran_service": iran_service,
            "iran_helper": iran_helper_service,
            "exit_helper": exit_helper_service,
            "route_selectable": True,
            "ping_probe": "20/20",
            "udp_probe": "20/20",
        }
        row = _member(db, tid)
        if not row:
            row = TunnelTransport(tunnel_id=tid, transport="ssh_relay", priority=200)
            db.add(row)
        row.priority = 200
        row.enabled = True
        row.status = "online"
        row.last_error = None
        row.last_healthy_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
        row.config_text = json.dumps(cfg, ensure_ascii=False)
        db.commit()
        return await verify_ssh_relay(tunnel, iran, db)

    except Exception as exc:
        db.rollback()
        row = _member(db, tid)
        if not row:
            row = TunnelTransport(
                tunnel_id=tid,
                transport="ssh_relay",
                priority=200,
            )
            db.add(row)
        row.enabled = False
        row.status = "offline"
        row.last_error = str(exc)[:700]
        row.updated_at = datetime.utcnow()
        db.commit()
        if ci:
            await _run(
                ci,
                f"systemctl disable --now {shlex.quote(iran_service)} {shlex.quote(iran_helper_service)} >/dev/null 2>&1 || true; ip link del {shlex.quote(iface)} >/dev/null 2>&1 || true",
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
        for conn in (ci, cr, ce):
            if conn:
                conn.close()
                await conn.wait_closed()
