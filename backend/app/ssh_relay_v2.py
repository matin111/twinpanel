from __future__ import annotations

import asyncio
import json
import shlex
from datetime import datetime
from pathlib import Path

from .models import Node, NodeAccess, TunnelTransport
from .ssh_relay import (
    _host_key,
    _known_host_name,
    _member,
    _udp_probe,
    _write,
    provision_ssh_relay as _provision_ssh_relay_v61,
    relay_addresses,
    relay_interface,
    relay_services,
    verify_ssh_relay,
)


# ============================================================
# TWINPANEL SSH RELAY V2 / SPLIT-HOP FALLBACK
#
# Primary path:
#   Iran OpenSSH -> ProxyJump relay -> final Exit TUN
#
# Some routes complete both SSH banner tests but still stall when OpenSSH
# combines ProxyJump and TunnelDevice in one process. For that exact failure,
# this module falls back automatically to two independent SSH processes:
#   1) Iran -> relay: local TCP forward to Exit SSH
#   2) Iran -> local forwarded port: point-to-point SSH TUN to Exit
#
# The final TCP connection still originates on the relay host, so the scoped
# Exit authorized_key/from= policy remains valid. Health is never fabricated:
# V7/V9/V10 still require the real tunnel interface, peer ping and egress.
# ============================================================


async def _run(conn, command: str, *, check: bool = True, timeout: int = 120):
    result = await conn.run(command, check=False, timeout=timeout)
    if check and result.exit_status != 0:
        raise RuntimeError(
            (result.stderr or result.stdout or "remote command failed")[-4000:]
        )
    return result


async def _ensure_tun(conn) -> None:
    await _run(
        conn,
        r"""
set -e
modprobe tun >/dev/null 2>&1 || true
install -d -m 755 /dev/net
if [ ! -c /dev/net/tun ]; then
    rm -f /dev/net/tun
    mknod /dev/net/tun c 10 200
    chmod 600 /dev/net/tun
fi
test -c /dev/net/tun
""",
        timeout=30,
    )


async def _install_relay_forwarding_policy(
    conn,
    *,
    tunnel_id: int,
    iran_public_ip: str,
) -> None:
    path = f"/etc/ssh/sshd_config.d/91-twinpanel-relay-hop-{int(tunnel_id)}.conf"
    content = (
        f"# TwinPanel relay hop {int(tunnel_id)}\n"
        f"Match User root Address {iran_public_ip}\n"
        "    AllowTcpForwarding yes\n"
    )

    quoted = shlex.quote(content)
    await _run(
        conn,
        f"""
set -e
install -d -m 755 /etc/ssh/sshd_config.d
printf '%s' {quoted} > {shlex.quote(path)}
chmod 600 {shlex.quote(path)}
sshd -t
VALUE=$(sshd -T -C user=root,addr={shlex.quote(iran_public_ip)},host=twinpanel-relay-hop | awk '/^allowtcpforwarding / {{print $2}}')
case "$VALUE" in
  yes|all|local) ;;
  *) echo "allowtcpforwarding=$VALUE" >&2; exit 41 ;;
esac
systemctl reload ssh 2>/dev/null || systemctl reload sshd
""",
        timeout=35,
    )


async def _install_exit_tunnel_policy(
    conn,
    *,
    tunnel_id: int,
    relay_public_ip: str,
) -> None:
    path = f"/etc/ssh/sshd_config.d/92-twinpanel-relay-exit-{int(tunnel_id)}.conf"
    content = (
        f"# TwinPanel relay exit {int(tunnel_id)}\n"
        f"Match User root Address {relay_public_ip}\n"
        "    PermitTunnel point-to-point\n"
    )

    quoted = shlex.quote(content)
    await _run(
        conn,
        f"""
set -e
install -d -m 755 /etc/ssh/sshd_config.d
printf '%s' {quoted} > {shlex.quote(path)}
chmod 600 {shlex.quote(path)}
sshd -t
VALUE=$(sshd -T -C user=root,addr={shlex.quote(relay_public_ip)},host=twinpanel-relay-exit | awk '/^permittunnel / {{print $2}}')
case "$VALUE" in
  yes|point-to-point) ;;
  *) echo "permittunnel=$VALUE" >&2; exit 42 ;;
esac
systemctl reload ssh 2>/dev/null || systemctl reload sshd
""",
        timeout=35,
    )


async def _prepare_relay_path(tunnel, iran: Node, relay: Node, exit_node: Node, db) -> None:
    from .routers.provision import ssh_connect_saved

    relay_access = (
        db.query(NodeAccess)
        .filter(NodeAccess.node_id == int(relay.id))
        .first()
    )
    exit_access = (
        db.query(NodeAccess)
        .filter(NodeAccess.node_id == int(exit_node.id))
        .first()
    )

    if not relay_access or not exit_access:
        raise RuntimeError("relay_saved_access_missing")

    ci = cr = ce = None
    try:
        ci = await ssh_connect_saved(iran, db)
        cr = await ssh_connect_saved(relay, db)
        ce = await ssh_connect_saved(exit_node, db)

        await _ensure_tun(ci)
        await _ensure_tun(ce)

        await _install_relay_forwarding_policy(
            cr,
            tunnel_id=int(tunnel.id),
            iran_public_ip=str(iran.public_ip),
        )
        await _install_exit_tunnel_policy(
            ce,
            tunnel_id=int(tunnel.id),
            relay_public_ip=str(relay.public_ip),
        )

        # TCP connect alone is insufficient for this failure mode. Require an
        # actual SSH identification line from the final Exit when observed
        # from the relay host.
        result = await _run(
            cr,
            f"""python3 - <<'PY2'
import socket
host={str(exit_node.public_ip)!r}
port={int(exit_access.ssh_port)}
s=socket.create_connection((host,port),timeout=8)
s.settimeout(8)
data=s.recv(256).decode('utf-8','replace').strip()
s.close()
print(data)
raise SystemExit(0 if data.startswith('SSH-') else 43)
PY2""",
            check=False,
            timeout=14,
        )
        if result.exit_status != 0:
            raise RuntimeError(
                f"relay_to_exit_ssh_banner_unreachable:{exit_node.public_ip}:{int(exit_access.ssh_port)}"
            )

    finally:
        for conn in (ci, cr, ce):
            if conn:
                conn.close()
                await conn.wait_closed()


async def _collect_failure_context(tunnel, iran: Node, relay: Node, exit_node: Node, db) -> str:
    from .routers.provision import ssh_connect_saved

    tid = int(tunnel.id)
    iface = relay_interface(tunnel)
    iran_service, iran_helper, exit_helper = relay_services(tunnel)
    hop_service = f"tp{tid}-relay-hop.service"
    base = f"/etc/twinpanel/ssh-relay/tunnel-{tid}"

    ci = cr = ce = None
    parts: list[str] = []

    async def snap(conn, label: str, command: str) -> None:
        try:
            result = await _run(conn, command, check=False, timeout=25)
            text = (result.stdout or "") + (result.stderr or "")
            text = text.strip().replace("\x00", "")
            if text:
                parts.append(f"[{label}] {text[-2200:]}")
        except Exception as exc:
            parts.append(f"[{label}] snapshot_error={type(exc).__name__}:{exc}")

    try:
        ci = await ssh_connect_saved(iran, db)
        cr = await ssh_connect_saved(relay, db)
        ce = await ssh_connect_saved(exit_node, db)

        await snap(
            ci,
            "iran",
            f"""
printf 'final='; systemctl is-active {shlex.quote(iran_service)} 2>/dev/null || true
printf 'hop='; systemctl is-active {shlex.quote(hop_service)} 2>/dev/null || true
printf 'helper='; systemctl is-active {shlex.quote(iran_helper)} 2>/dev/null || true
ip -br addr show {shlex.quote(iface)} 2>&1 || true
journalctl -u {shlex.quote(hop_service)} -n 25 --no-pager -o cat 2>&1 || true
journalctl -u {shlex.quote(iran_service)} -n 35 --no-pager -o cat 2>&1 || true
if [ -f {shlex.quote(base + '/ssh_config')} ]; then
  ssh -G -F {shlex.quote(base + '/ssh_config')} tp{tid}-exit 2>/dev/null | grep -E '^(hostname|port|proxyjump|tunnel |tunneldevice|identityfile) ' || true
fi
if [ -f {shlex.quote(base + '/split_exit_config')} ]; then
  ssh -G -F {shlex.quote(base + '/split_exit_config')} tp{tid}-exit-local 2>/dev/null | grep -E '^(hostname|port|hostkeyalias|tunnel |tunneldevice|identityfile) ' || true
fi
""",
        )

        await snap(
            cr,
            "relay",
            f"""
sshd -T -C user=root,addr={shlex.quote(str(iran.public_ip))},host=twinpanel-relay-hop 2>/dev/null | grep -E '^(allowtcpforwarding|disableforwarding|permitopen|pubkeyauthentication|permitrootlogin) ' || true
journalctl -u ssh -n 35 --no-pager -o cat 2>&1 || journalctl -u sshd -n 35 --no-pager -o cat 2>&1 || true
""",
        )

        await snap(
            ce,
            "exit",
            f"""
sshd -T -C user=root,addr={shlex.quote(str(relay.public_ip))},host=twinpanel-relay-exit 2>/dev/null | grep -E '^(permittunnel|pubkeyauthentication|permitrootlogin) ' || true
ip -br addr show {shlex.quote(iface)} 2>&1 || true
printf 'helper='; systemctl is-active {shlex.quote(exit_helper)} 2>/dev/null || true
journalctl -u ssh -n 35 --no-pager -o cat 2>&1 || journalctl -u sshd -n 35 --no-pager -o cat 2>&1 || true
""",
        )

    finally:
        for conn in (ci, cr, ce):
            if conn:
                conn.close()
                await conn.wait_closed()

    return " | ".join(parts)[-6500:]


async def _pick_local_port(ci, tunnel_id: int) -> int:
    start = 47000 + (int(tunnel_id) % 1000)
    result = await _run(
        ci,
        f"""python3 - <<'PY2'
import socket
start={start}
for port in range(start, min(start+40, 65535)):
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1',port))
    except OSError:
        s.close()
        continue
    s.close()
    print(port)
    raise SystemExit(0)
raise SystemExit(44)
PY2""",
        timeout=15,
    )
    return int(result.stdout.strip())


async def _provision_split_hop(tunnel, iran: Node, relay: Node, exit_node: Node, db) -> dict:
    from .routers.provision import ssh_connect_saved

    relay_access = (
        db.query(NodeAccess)
        .filter(NodeAccess.node_id == int(relay.id))
        .first()
    )
    exit_access = (
        db.query(NodeAccess)
        .filter(NodeAccess.node_id == int(exit_node.id))
        .first()
    )
    if not relay_access or not exit_access:
        raise RuntimeError("split_hop_saved_access_missing")

    tid = int(tunnel.id)
    number = 100 + tid
    iface = relay_interface(tunnel)
    network, iran_ip, exit_ip = relay_addresses(tunnel)
    iran_service, iran_helper_service, exit_helper_service = relay_services(tunnel)
    hop_service = f"tp{tid}-relay-hop.service"
    base = f"/etc/twinpanel/ssh-relay/tunnel-{tid}"

    ci = cr = ce = None
    local_port = None

    try:
        ci = await ssh_connect_saved(iran, db)
        cr = await ssh_connect_saved(relay, db)
        ce = await ssh_connect_saved(exit_node, db)

        await _ensure_tun(ci)
        await _ensure_tun(ce)

        # The V61 attempt normally created this key. Keep the fallback
        # independently repairable if it did not.
        await _run(
            ci,
            f"""
set -e
install -d -m 700 {shlex.quote(base)}
if [ ! -s {shlex.quote(base + '/id_ed25519')} ]; then
  ssh-keygen -q -t ed25519 -N '' -f {shlex.quote(base + '/id_ed25519')}
fi
chmod 600 {shlex.quote(base + '/id_ed25519')}
""",
        )

        # Host keys are pinned. No StrictHostKeyChecking bypass is used.
        relay_key = await _host_key(cr)
        exit_key = await _host_key(ce)
        known_hosts = (
            f"{_known_host_name(str(relay.public_ip), int(relay_access.ssh_port))} {relay_key}\n"
            f"{_known_host_name(str(exit_node.public_ip), int(exit_access.ssh_port))} {exit_key}\n"
        )
        await _write(ci, base + "/known_hosts", known_hosts, "600")

        local_port = await _pick_local_port(ci, tid)

        hop_cfg = f"""Host tp{tid}-hop-split
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
    ExitOnForwardFailure yes
    RequestTTY no
"""

        exit_cfg = f"""Host tp{tid}-exit-local
    HostName 127.0.0.1
    Port {int(local_port)}
    HostKeyAlias {exit_node.public_ip}
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
    ExitOnForwardFailure yes
    Tunnel point-to-point
    TunnelDevice {number}:{number}
    RequestTTY no
"""

        await _write(ci, base + "/split_hop_config", hop_cfg, "600")
        await _write(ci, base + "/split_exit_config", exit_cfg, "600")

        hop_unit = f"""[Unit]
Description=TwinPanel Tunnel {tid} SSH Relay Split Hop via Node {int(relay.id)}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/ssh -F {base}/split_hop_config -N -L 127.0.0.1:{int(local_port)}:{exit_node.public_ip}:{int(exit_access.ssh_port)} tp{tid}-hop-split
Restart=always
RestartSec=2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

        final_unit = f"""[Unit]
Description=TwinPanel Tunnel {tid} SSH Relay Split Final
After=network-online.target {hop_service} {iran_helper_service}
Requires={hop_service}
Wants=network-online.target {iran_helper_service}

[Service]
Type=simple
ExecStart=/usr/bin/ssh -F {base}/split_exit_config -N tp{tid}-exit-local
Restart=always
RestartSec=2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

        await _write(ci, f"/etc/systemd/system/{hop_service}", hop_unit, "644")
        await _write(ci, f"/etc/systemd/system/{iran_service}", final_unit, "644")

        # V61 already installed the interface helper unit files. Refuse to
        # fabricate them here if they are absent; that means the base
        # provisioner failed before split-hop is a meaningful fallback.
        helper_check = await _run(
            ci,
            f"test -s /etc/systemd/system/{shlex.quote(iran_helper_service)}",
            check=False,
        )
        exit_helper_check = await _run(
            ce,
            f"test -s /etc/systemd/system/{shlex.quote(exit_helper_service)}",
            check=False,
        )
        if helper_check.exit_status != 0 or exit_helper_check.exit_status != 0:
            raise RuntimeError("split_hop_interface_helpers_missing")

        await _run(
            ce,
            f"systemctl daemon-reload; systemctl enable --now {shlex.quote(exit_helper_service)} >/dev/null",
        )
        await _run(
            ci,
            f"""
set -e
systemctl daemon-reload
systemctl disable --now {shlex.quote(iran_service)} {shlex.quote(hop_service)} >/dev/null 2>&1 || true
systemctl enable --now {shlex.quote(iran_helper_service)} >/dev/null
systemctl enable --now {shlex.quote(hop_service)} >/dev/null
""",
        )

        # The first hop must expose the actual Exit SSH banner locally before
        # the TUN session is started.
        banner_ok = False
        for _ in range(20):
            banner = await _run(
                ci,
                f"""python3 - <<'PY2'
import socket
try:
    s=socket.create_connection(('127.0.0.1',{int(local_port)}),timeout=2)
    s.settimeout(2)
    data=s.recv(128).decode('utf-8','replace').strip()
    s.close()
    print(data)
    raise SystemExit(0 if data.startswith('SSH-') else 1)
except Exception:
    raise SystemExit(1)
PY2""",
                check=False,
                timeout=5,
            )
            if banner.exit_status == 0:
                banner_ok = True
                break
            await asyncio.sleep(1)
        if not banner_ok:
            raise RuntimeError("split_hop_local_exit_banner_not_ready")

        await _run(
            ci,
            f"systemctl enable {shlex.quote(iran_service)} >/dev/null; systemctl restart {shlex.quote(iran_service)}",
        )

        ready = False
        for _ in range(35):
            probe = await _run(
                ci,
                f"systemctl is-active --quiet {shlex.quote(hop_service)} && systemctl is-active --quiet {shlex.quote(iran_service)} && ip addr show {shlex.quote(iface)} 2>/dev/null | grep -q {shlex.quote(iran_ip)} && ping -I {shlex.quote(iface)} -c 1 -W 1 {shlex.quote(exit_ip)} >/dev/null 2>&1",
                check=False,
                timeout=8,
            )
            if probe.exit_status == 0:
                ready = True
                break
            await asyncio.sleep(1)
        if not ready:
            raise RuntimeError("split_hop_relay_interface_did_not_become_ready")

        sustained = await _run(
            ci,
            f"LC_ALL=C ping -I {shlex.quote(iface)} -c 20 -i 0.20 -W 2 -s 1000 {shlex.quote(exit_ip)}",
            check=False,
            timeout=45,
        )
        if sustained.exit_status != 0 or "0% packet loss" not in sustained.stdout:
            raise RuntimeError(
                "split_hop_sustained_ping_failed: " + sustained.stdout[-1600:]
            )

        await _udp_probe(ci, ce, tunnel, iran_ip, exit_ip)

        cfg = {
            "type": "ssh_relay",
            "mode": "split_hop",
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
            "hop_service": hop_service,
            "local_forward_port": int(local_port),
            "route_selectable": True,
            "ping_probe": "20/20",
            "udp_probe": "20/20",
        }

        row = _member(db, tid)
        if not row:
            row = TunnelTransport(
                tunnel_id=tid,
                transport="ssh_relay",
                priority=300,
            )
            db.add(row)
        row.priority = 300
        row.enabled = True
        row.status = "online"
        row.last_error = None
        row.last_healthy_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
        row.config_text = json.dumps(cfg, ensure_ascii=False)
        db.commit()

        result = await verify_ssh_relay(tunnel, iran, db)
        result["mode"] = "split_hop"
        result["relay_node_id"] = int(relay.id)
        return result

    except Exception:
        db.rollback()
        row = _member(db, tid)
        if row:
            row.priority = 300
            row.enabled = False
            row.status = "offline"
            row.updated_at = datetime.utcnow()
            db.commit()

        if ci:
            await _run(
                ci,
                f"systemctl disable --now {shlex.quote(iran_service)} {shlex.quote(hop_service)} {shlex.quote(iran_helper_service)} >/dev/null 2>&1 || true; ip link del {shlex.quote(iface)} >/dev/null 2>&1 || true",
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


async def provision_ssh_relay_v2(tunnel, iran: Node, relay: Node, exit_node: Node, db) -> dict:
    """Prepare SSH capabilities and recover through either relay topology.

    The original one-process ProxyJump+TunnelDevice path is attempted first.
    If it reaches the known interface/banner failure, automatically retry with
    the split-hop topology. Both paths must pass real tunnel/UDP probes.
    """

    await _prepare_relay_path(
        tunnel,
        iran,
        relay,
        exit_node,
        db,
    )

    try:
        return await _provision_ssh_relay_v61(
            tunnel,
            iran,
            relay,
            exit_node,
            db,
        )

    except asyncio.CancelledError:
        raise

    except Exception as primary_exc:
        primary_text = str(primary_exc)

        split_candidate = (
            "interface did not become ready" in primary_text.lower()
            or "banner" in primary_text.lower()
        )

        if split_candidate:
            print(
                f"[SSHRelayV2] SPLIT_HOP_FALLBACK tunnel={int(tunnel.id)} relay_node={int(relay.id)}",
                flush=True,
            )
            try:
                return await _provision_split_hop(
                    tunnel,
                    iran,
                    relay,
                    exit_node,
                    db,
                )
            except asyncio.CancelledError:
                raise
            except Exception as split_exc:
                context = await _collect_failure_context(
                    tunnel,
                    iran,
                    relay,
                    exit_node,
                    db,
                )
                raise RuntimeError(
                    "proxyjump_failed="
                    f"{type(primary_exc).__name__}:{primary_exc}; "
                    "split_hop_failed="
                    f"{type(split_exc).__name__}:{split_exc}; "
                    f"diagnostics={context}"
                ) from split_exc

        context = await _collect_failure_context(
            tunnel,
            iran,
            relay,
            exit_node,
            db,
        )
        raise RuntimeError(
            f"{type(primary_exc).__name__}:{primary_exc}; diagnostics={context}"
        ) from primary_exc
