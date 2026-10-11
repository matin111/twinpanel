from __future__ import annotations

import asyncio
import shlex
from pathlib import Path

from .models import Node, NodeAccess
from .ssh_relay import (
    provision_ssh_relay as _provision_ssh_relay_v61,
    relay_interface,
    relay_services,
)


# ============================================================
# TWINPANEL SSH RELAY V2
#
# Hardened wrapper around the existing generic SSH relay installer.
# It prepares the two server-side capabilities the original installer
# implicitly depended on:
#   * TCP forwarding on the relay hop for ProxyJump/direct-tcpip;
#   * point-to-point TUN forwarding on the final Exit.
# It also makes sure /dev/net/tun exists on both tunnel endpoints and
# captures useful, secret-free diagnostics if provisioning still fails.
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

        # TUN is only required on the actual tunnel endpoints. The relay hop
        # only forwards the SSH TCP stream.
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

        # Prove that the relay host itself can reach the final SSH endpoint.
        # This is intentionally a TCP-only preflight and does not fabricate
        # tunnel health.
        result = await _run(
            cr,
            f"timeout 8 bash -lc '</dev/tcp/{shlex.quote(str(exit_node.public_ip))}/{int(exit_access.ssh_port)}'",
            check=False,
            timeout=12,
        )
        if result.exit_status != 0:
            raise RuntimeError(
                f"relay_to_exit_tcp_unreachable:{exit_node.public_ip}:{int(exit_access.ssh_port)}"
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
printf 'service='; systemctl is-active {shlex.quote(iran_service)} 2>/dev/null || true
printf 'helper='; systemctl is-active {shlex.quote(iran_helper)} 2>/dev/null || true
ip -br addr show {shlex.quote(iface)} 2>&1 || true
journalctl -u {shlex.quote(iran_service)} -n 35 --no-pager -o cat 2>&1 || true
if [ -f {shlex.quote(base + '/ssh_config')} ]; then
  ssh -G -F {shlex.quote(base + '/ssh_config')} tp{tid}-exit 2>/dev/null | grep -E '^(hostname|port|proxyjump|tunnel |tunneldevice|identityfile) ' || true
fi
""",
        )

        await snap(
            cr,
            "relay",
            f"""
sshd -T -C user=root,addr={shlex.quote(str(iran.public_ip))},host=twinpanel-relay-hop 2>/dev/null | grep -E '^(allowtcpforwarding|permitopen|pubkeyauthentication|permitrootlogin) ' || true
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


async def provision_ssh_relay_v2(tunnel, iran: Node, relay: Node, exit_node: Node, db) -> dict:
    """Prepare SSH server capabilities, then use the proven V61 installer.

    If the first attempt still fails, the raised error includes a compact
    diagnostic snapshot so the autonomous manager can persist actionable
    failure context instead of only "interface did not become ready".
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
    except Exception as exc:
        context = await _collect_failure_context(
            tunnel,
            iran,
            relay,
            exit_node,
            db,
        )
        raise RuntimeError(
            f"{type(exc).__name__}:{exc}; diagnostics={context}"
        ) from exc
