from __future__ import annotations

import asyncio
import base64
import re
import shlex
from datetime import datetime

from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Node, Tunnel, TunnelTransport
from .ssh_tunnel import (
    ssh_tunnel_addresses,
    ssh_tunnel_backhaul_values,
    ssh_tunnel_interface,
    ssh_tunnel_number,
    ssh_tunnel_services,
    ssh_tunnel_user,
    verify_ssh_tunnel,
)
from .tp2027_provision import TP2027_PRIORITY, install_tp2027_overlays


EXPECTED_ORDER = (
    "quic_2027",
    "arq_2027",
    "kcp_2027",
    "tcp_2027",
    "mtunnel",
    "backhaul",
    "ssh_tun",
)

TLS_PUBLIC_PORTS = (
    9443,
    10443,
    8443,
    2053,
    2083,
    443,
)


async def _run(conn, script: str, label: str, timeout: int = 90) -> str:
    result = await conn.run(
        script,
        check=False,
        timeout=timeout,
    )

    if result.exit_status != 0:
        message = (
            result.stderr
            or result.stdout
            or "unknown error"
        )
        raise RuntimeError(
            f"{label}: {message[-1800:]}"
        )

    return (result.stdout or "").strip()


async def _write_remote(
    conn,
    path: str,
    content: str,
    mode: str = "0600",
) -> None:
    encoded = base64.b64encode(
        content.encode("utf-8")
    ).decode("ascii")

    await _run(
        conn,
        f"""
set -e
install -d -m 0700 {shlex.quote(path.rsplit('/', 1)[0])}
printf '%s' {shlex.quote(encoded)} | base64 -d > {shlex.quote(path)}
chmod {mode} {shlex.quote(path)}
""",
        f"write:{path}",
    )


async def _ensure_stunnel(conn) -> str:
    output = await _run(
        conn,
        r'''
set -e
if command -v stunnel4 >/dev/null 2>&1; then
    command -v stunnel4
    exit 0
fi
if command -v stunnel >/dev/null 2>&1; then
    command -v stunnel
    exit 0
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y stunnel4 >/dev/null
command -v stunnel4 || command -v stunnel
''',
        "install_stunnel",
        timeout=210,
    )
    binary = output.splitlines()[-1].strip()
    if not binary:
        raise RuntimeError("stunnel_binary_missing")
    return binary


async def _select_exit_port(conn, tunnel_id: int) -> int:
    candidates = list(TLS_PUBLIC_PORTS)
    candidates.extend(
        [30000 + (int(tunnel_id) % 1000), 31000 + (int(tunnel_id) % 1000)]
    )

    ports = " ".join(str(item) for item in candidates)
    output = await _run(
        conn,
        f'''
set -e
for P in {ports}; do
    if ! ss -H -lnt | awk '{{print $4}}' | grep -Eq ":${{P}}$"; then
        echo "$P"
        exit 0
    fi
done
exit 9
''',
        "select_tls_port",
    )
    return int(output.splitlines()[-1])


async def _select_local_port(conn, tunnel_id: int) -> int:
    candidates = (
        22000 + (int(tunnel_id) % 1000),
        23000 + (int(tunnel_id) % 1000),
        24000 + (int(tunnel_id) % 1000),
    )
    ports = " ".join(str(item) for item in candidates)
    output = await _run(
        conn,
        f'''
set -e
for P in {ports}; do
    if ! ss -H -lnt | awk '{{print $4}}' | grep -Eq ":${{P}}$"; then
        echo "$P"
        exit 0
    fi
done
exit 9
''',
        "select_local_tls_port",
    )
    return int(output.splitlines()[-1])


async def _install_ssh_tls_fallback(
    tunnel: Tunnel,
    iran: Node,
    exit_node: Node,
    db: Session,
    plain_error: str,
) -> dict:
    from .routers.provision import ssh_connect_saved

    number = ssh_tunnel_number(tunnel)
    iface = ssh_tunnel_interface(tunnel)
    user = ssh_tunnel_user(tunnel)
    _, iran_addr, exit_addr = ssh_tunnel_addresses(tunnel)
    iran_ip = iran_addr.split("/", 1)[0]
    exit_ip = exit_addr.split("/", 1)[0]
    iran_service, exit_service = ssh_tunnel_services(tunnel)

    exit_public_ip = str(exit_node.public_ip or "").strip()
    iran_public_ip = str(iran.public_ip or "").strip()
    exit_ssh_port = int(getattr(exit_node, "ssh_port", 22) or 22)

    if not exit_public_ip:
        raise RuntimeError("tls_fallback_exit_public_ip_missing")

    key_dir = f"/etc/twinpanel/tp{number}-ssh"
    key_path = f"{key_dir}/id_ed25519"
    known_hosts = f"{key_dir}/known_hosts"

    tls_dir = f"/etc/twinpanel/tp{number}-ssh-tls"
    server_conf = f"{tls_dir}/server.conf"
    client_conf = f"{tls_dir}/client.conf"
    server_cert = f"{tls_dir}/server.crt"
    server_key = f"{tls_dir}/server.key"
    trusted_cert = f"{tls_dir}/exit.crt"

    server_unit = f"tp{number}-ssh-tls-server.service"
    client_unit = f"tp{number}-ssh-tls-client.service"

    exit_helper = f"/usr/local/sbin/tp{number}-exit-up"
    iran_helper = f"/usr/local/sbin/tp{number}-iran-up"
    exit_unit_path = f"/etc/systemd/system/{exit_service}"
    iran_unit_path = f"/etc/systemd/system/{iran_service}"

    ci = None
    ce = None

    try:
        ci = await ssh_connect_saved(iran, db)
        ce = await ssh_connect_saved(exit_node, db)

        iran_stunnel, exit_stunnel = await asyncio.gather(
            _ensure_stunnel(ci),
            _ensure_stunnel(ce),
        )

        public_key = await _run(
            ci,
            f'''
set -e
install -d -m 0700 {shlex.quote(key_dir)}
if [ ! -s {shlex.quote(key_path)} ]; then
    ssh-keygen -q -t ed25519 -N '' -f {shlex.quote(key_path)}
fi
chmod 0600 {shlex.quote(key_path)}
chmod 0644 {shlex.quote(key_path)}.pub
cat {shlex.quote(key_path)}.pub
''',
            "tls_iran_key",
        )
        public_key = public_key.strip().splitlines()[-1]
        if not public_key.startswith("ssh-ed25519 "):
            raise RuntimeError("tls_invalid_public_key")

        host_key = await _run(
            ce,
            r'''
set -e
if [ -s /etc/ssh/ssh_host_ed25519_key.pub ]; then
    awk '{print $1 " " $2}' /etc/ssh/ssh_host_ed25519_key.pub
else
    awk '{print $1 " " $2}' /etc/ssh/ssh_host_rsa_key.pub
fi
''',
            "tls_exit_host_key",
        )
        host_key = host_key.strip().splitlines()[-1]

        backhaul = ssh_tunnel_backhaul_values(tunnel)
        source_ips = ["127.0.0.1", "::1"]
        if iran_public_ip:
            source_ips.append(iran_public_ip)
        bh_iran = str(backhaul.get("iran_ip") or "").strip()
        if bh_iran:
            source_ips.append(bh_iran)
        source_ips = list(dict.fromkeys(source_ips))
        auth_key = f'from="{",".join(source_ips)}" {public_key}'

        await _run(
            ce,
            f'''
set -e
groupadd -f twinpanel-tun
if ! id -u {shlex.quote(user)} >/dev/null 2>&1; then
    useradd -m -s /bin/bash -g twinpanel-tun {shlex.quote(user)}
fi
usermod -a -G twinpanel-tun {shlex.quote(user)}
TP_RANDOM_PASSWORD="$(openssl rand -hex 48)"
TP_RANDOM_HASH="$(openssl passwd -6 "$TP_RANDOM_PASSWORD")"
usermod -p "$TP_RANDOM_HASH" {shlex.quote(user)}
unset TP_RANDOM_PASSWORD TP_RANDOM_HASH
install -d -m 0700 -o {shlex.quote(user)} -g twinpanel-tun /home/{shlex.quote(user)}/.ssh
printf '%s\n' {shlex.quote(auth_key)} > /home/{shlex.quote(user)}/.ssh/authorized_keys
chown {shlex.quote(user)}:twinpanel-tun /home/{shlex.quote(user)}/.ssh/authorized_keys
chmod 0600 /home/{shlex.quote(user)}/.ssh/authorized_keys
if ! grep -q '^# BEGIN TWINPANEL TUNNEL GROUP$' /etc/ssh/sshd_config; then
cat >> /etc/ssh/sshd_config <<'EOF'

# BEGIN TWINPANEL TUNNEL GROUP
Match Group twinpanel-tun
    PermitTunnel point-to-point
    PubkeyAuthentication yes
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    AllowTcpForwarding no
    AllowAgentForwarding no
    X11Forwarding no
    PermitTTY no
    PermitUserRC no
# END TWINPANEL TUNNEL GROUP
EOF
fi
/usr/sbin/sshd -t
systemctl reload ssh 2>/dev/null || systemctl reload sshd
''',
            "tls_exit_account",
        )

        await _run(
            ce,
            f'''
set -e
cat > {shlex.quote(exit_helper)} <<'EOF'
#!/bin/bash
set -e
modprobe tun
if ! ip link show {iface} >/dev/null 2>&1; then
    ip tuntap add dev {iface} mode tun user {user}
fi
ip addr flush dev {iface}
ip addr add {exit_addr} peer {iran_ip} dev {iface}
ip link set dev {iface} mtu 1400 up
EOF
chmod 0755 {shlex.quote(exit_helper)}
cat > {shlex.quote(exit_unit_path)} <<'EOF'
[Unit]
Description=TwinPanel SSH Tunnel Exit {number}
After=network-pre.target
Before=ssh.service

[Service]
Type=oneshot
ExecStart={exit_helper}
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable {shlex.quote(exit_service)} >/dev/null
systemctl restart {shlex.quote(exit_service)}
''',
            "tls_exit_tun",
        )

        public_port = await _select_exit_port(ce, int(tunnel.id))
        local_port = await _select_local_port(ci, int(tunnel.id))

        await _run(
            ce,
            f'''
set -e
install -d -m 0700 {shlex.quote(tls_dir)}
openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 3650 \
  -subj '/CN=twinpanel-ssh-tls-{int(tunnel.id)}' \
  -addext 'subjectAltName=IP:{exit_public_ip}' \
  -keyout {shlex.quote(server_key)} \
  -out {shlex.quote(server_cert)} >/dev/null 2>&1
chmod 0600 {shlex.quote(server_key)}
chmod 0644 {shlex.quote(server_cert)}
cat {shlex.quote(server_cert)}
''',
            "tls_certificate",
        )
        cert_text = await _run(
            ce,
            f"cat {shlex.quote(server_cert)}",
            "tls_read_certificate",
        )
        await _write_remote(ci, trusted_cert, cert_text + "\n", "0644")

        server_cfg = f"""foreground = yes
client = no
sslVersionMin = TLSv1.2

[tp{number}]
accept = 0.0.0.0:{public_port}
connect = 127.0.0.1:{exit_ssh_port}
cert = {server_cert}
key = {server_key}
TIMEOUTclose = 0
socket = l:TCP_NODELAY=1
socket = r:TCP_NODELAY=1
"""
        client_cfg = f"""foreground = yes
client = yes
verify = 2
CAfile = {trusted_cert}
sslVersionMin = TLSv1.2

[tp{number}]
accept = 127.0.0.1:{local_port}
connect = {exit_public_ip}:{public_port}
TIMEOUTclose = 0
socket = l:TCP_NODELAY=1
socket = r:TCP_NODELAY=1
"""

        await _write_remote(ce, server_conf, server_cfg, "0600")
        await _write_remote(ci, client_conf, client_cfg, "0600")

        server_unit_text = f"""[Unit]
Description=TwinPanel SSH TLS server {number}
After=network-online.target ssh.service
Wants=network-online.target

[Service]
Type=simple
ExecStart={exit_stunnel} {server_conf}
Restart=always
RestartSec=2
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
"""
        client_unit_text = f"""[Unit]
Description=TwinPanel SSH TLS client {number}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={iran_stunnel} {client_conf}
Restart=always
RestartSec=2
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
"""

        await _write_remote(
            ce,
            f"/etc/systemd/system/{server_unit}",
            server_unit_text,
            "0644",
        )
        await _write_remote(
            ci,
            f"/etc/systemd/system/{client_unit}",
            client_unit_text,
            "0644",
        )

        await _run(
            ce,
            f'''
set -e
systemctl daemon-reload
systemctl enable {shlex.quote(server_unit)} >/dev/null
systemctl restart {shlex.quote(server_unit)}
sleep 2
systemctl is-active {shlex.quote(server_unit)}
''',
            "tls_server_service",
        )

        await _run(
            ci,
            f'''
set -e
systemctl daemon-reload
systemctl enable {shlex.quote(client_unit)} >/dev/null
systemctl restart {shlex.quote(client_unit)}
sleep 2
systemctl is-active {shlex.quote(client_unit)}
timeout 10 openssl s_client \
  -connect 127.0.0.1:{local_port} \
  -servername twinpanel \
  </dev/null 2>/dev/null | grep -q 'BEGIN CERTIFICATE'
''',
            "tls_client_service",
        )

        host_targets = [
            exit_public_ip,
            f"[{exit_public_ip}]:{exit_ssh_port}",
            f"[{exit_public_ip}]:{local_port}",
        ]
        known_lines = "\n".join(
            f"{target} {host_key}"
            for target in dict.fromkeys(host_targets)
        )
        await _write_remote(ci, known_hosts, known_lines + "\n", "0600")

        await _run(
            ci,
            f'''
set -e
cat > {shlex.quote(iran_helper)} <<'EOF'
#!/bin/bash
set -e
for i in $(seq 1 25); do
    if ip link show {iface} >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
ip link show {iface} >/dev/null 2>&1
ip addr flush dev {iface}
ip addr add {iran_addr} peer {exit_ip} dev {iface}
ip link set dev {iface} mtu 1400 up
EOF
chmod 0755 {shlex.quote(iran_helper)}
cat > {shlex.quote(iran_unit_path)} <<'EOF'
[Unit]
Description=TwinPanel SSH Tunnel {number} over TLS
Requires={client_unit}
After=network-online.target {client_unit}
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart=/usr/bin/ssh -p {local_port} -i {key_path} -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o StrictHostKeyChecking=yes -o UserKnownHostsFile={known_hosts} -o HostKeyAlias={exit_public_ip} -o Tunnel=point-to-point -o ExitOnForwardFailure=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 -o ServerAliveInterval=5 -o ServerAliveCountMax=3 -o TCPKeepAlive=yes -o Compression=no -o IPQoS=none -w {number}:{number} -N {user}@127.0.0.1
ExecStartPost={iran_helper}
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable {shlex.quote(iran_service)} >/dev/null
systemctl restart {shlex.quote(iran_service)}
''',
            "tls_iran_ssh_service",
        )

        await asyncio.sleep(5)
        verified = await verify_ssh_tunnel(
            tunnel,
            iran,
            exit_node,
            db,
        )

        verified["underlay"] = "tls"
        verified["tls_public_port"] = public_port
        verified["tls_local_port"] = local_port
        verified["plain_error"] = plain_error[:1200]
        return verified

    finally:
        if ci:
            ci.close()
            await ci.wait_closed()
        if ce:
            ce.close()
            await ce.wait_closed()


async def install_ssh_transport_managed(
    tunnel_id: int,
    db: Session,
):
    """Install SSH TUN, automatically falling back to TLS when plain SSH fails."""
    from .routers import tunnels as core

    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")

    iran = db.get(Node, int(tunnel.iran_node_id))
    exit_node = db.get(Node, int(tunnel.exit_node_id))
    if iran is None or exit_node is None:
        raise RuntimeError("tunnel_node_missing")

    try:
        result = await core.install_ssh_transport(
            int(tunnel_id),
            db,
        )
        if isinstance(result, dict):
            result.setdefault("underlay", "plain")
        return result
    except Exception as exc:
        db.rollback()
        plain_error = str(exc)

    result = await _install_ssh_tls_fallback(
        tunnel,
        iran,
        exit_node,
        db,
        plain_error,
    )

    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == "ssh_tun",
        )
        .first()
    )
    if row is not None:
        row.enabled = True
        row.status = "online"
        row.last_error = None
        row.updated_at = datetime.utcnow()
        db.commit()

    return result


def diagnose_managed_tunnel(
    tunnel_id: int,
    db: Session,
) -> dict:
    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")

    rows = {
        str(row.transport).strip().lower(): row
        for row in (
            db.query(TunnelTransport)
            .filter(TunnelTransport.tunnel_id == int(tunnel_id))
            .all()
        )
    }

    backhaul = rows.get("backhaul")
    backhaul_online = bool(
        backhaul
        and bool(backhaul.enabled)
        and str(backhaul.status or "").lower() == "online"
    )

    transports: list[dict] = []
    repair_needed: list[str] = []

    for name in EXPECTED_ORDER:
        row = rows.get(name)
        status = str(row.status or "missing").lower() if row else "missing"
        enabled = bool(row.enabled) if row else False
        issue_code = None

        if name in TP2027_PRIORITY and not backhaul_online:
            issue_code = "carrier_down"
        elif row is None:
            issue_code = "not_installed"
        elif not enabled:
            issue_code = "disabled"
        elif status != "online":
            issue_code = "unhealthy"

        if issue_code:
            repair_needed.append(name)

        transports.append(
            {
                "transport": name,
                "priority": getattr(row, "priority", None),
                "enabled": enabled,
                "status": status,
                "latency_ms": getattr(row, "latency_ms", None),
                "last_error": getattr(row, "last_error", None),
                "issue_code": issue_code,
                "dependency": "backhaul" if name in TP2027_PRIORITY else None,
            }
        )

    return {
        "ok": True,
        "tunnel_id": int(tunnel.id),
        "mode": str(getattr(tunnel, "mode", "auto") or "auto"),
        "status": str(getattr(tunnel, "status", "offline")),
        "active_transport": getattr(tunnel, "active_transport", None),
        "preferred_transport": getattr(tunnel, "preferred_transport", None),
        "backhaul_online": backhaul_online,
        "repair_needed": repair_needed,
        "healthy": not repair_needed,
        "transports": transports,
    }


async def _repair_base_job(
    name: str,
    tunnel_id: int,
) -> tuple[str, bool, str | None, object | None]:
    from .routers import tunnels as core

    installers = {
        "mtunnel": core.install_mtunnel_transport,
        "backhaul": core.install_backhaul_transport,
        "ssh_tun": install_ssh_transport_managed,
    }

    db = SessionLocal()
    try:
        try:
            result = await asyncio.wait_for(
                installers[name](int(tunnel_id), db),
                timeout=240 if name == "ssh_tun" else 160,
            )
            db.expire_all()
            row = (
                db.query(TunnelTransport)
                .filter(
                    TunnelTransport.tunnel_id == int(tunnel_id),
                    TunnelTransport.transport == name,
                )
                .first()
            )
            online = bool(
                row
                and bool(row.enabled)
                and str(row.status or "").lower() == "online"
            )
            return (
                name,
                online,
                None if online else "installer_finished_but_transport_not_online",
                result,
            )
        except Exception as exc:
            db.rollback()
            return name, False, str(exc)[:1800], None
    finally:
        db.close()


async def repair_managed_tunnel(
    tunnel_id: int,
    db: Session,
) -> dict:
    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")

    # AUTO is the control-plane contract. Health/active selection stays owned
    # by Transport Manager V7; this routine only installs and repairs runtime.
    tunnel.mode = "auto"
    tunnel.is_active = True
    db.commit()

    before = diagnose_managed_tunnel(int(tunnel_id), db)
    need = set(before["repair_needed"])

    base_targets = [
        name
        for name in ("mtunnel", "backhaul", "ssh_tun")
        if name in need
    ]

    base_results: dict[str, object] = {}
    errors: dict[str, str] = {}

    if base_targets:
        settled = await asyncio.gather(
            *(
                _repair_base_job(name, int(tunnel_id))
                for name in base_targets
            )
        )
        for name, online, error, result in settled:
            if result is not None:
                base_results[name] = result
            if not online and error:
                errors[name] = error

    db.expire_all()
    rows = {
        str(row.transport).strip().lower(): row
        for row in (
            db.query(TunnelTransport)
            .filter(TunnelTransport.tunnel_id == int(tunnel_id))
            .all()
        )
    }
    backhaul = rows.get("backhaul")
    backhaul_online = bool(
        backhaul
        and bool(backhaul.enabled)
        and str(backhaul.status or "").lower() == "online"
    )

    overlay_result = None
    if backhaul_online:
        overlay_need = any(name in need for name in TP2027_PRIORITY)
        if overlay_need:
            try:
                overlay_result = await asyncio.wait_for(
                    install_tp2027_overlays(int(tunnel_id), db),
                    timeout=240,
                )
            except Exception as exc:
                db.rollback()
                message = str(exc)[:1800]
                for name in TP2027_PRIORITY:
                    errors[name] = message
    else:
        for name in TP2027_PRIORITY:
            if name in need:
                errors.setdefault(name, "carrier_down: backhaul is not online")

    # Give V7 a small window to consume the repaired runtime; never fabricate
    # peer reachability or active transport here.
    await asyncio.sleep(3)
    db.expire_all()
    after = diagnose_managed_tunnel(int(tunnel_id), db)

    return {
        "ok": True,
        "tunnel_id": int(tunnel_id),
        "mode": "auto",
        "before": before,
        "after": after,
        "base_results": base_results,
        "tp2027_result": overlay_result,
        "errors": errors,
    }
