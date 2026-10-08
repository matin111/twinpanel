from __future__ import annotations

import asyncio
import shlex

from .ssh_tunnel import (
    ssh_tunnel_addresses,
    ssh_tunnel_backhaul_values,
    ssh_tunnel_interface,
    ssh_tunnel_number,
    ssh_tunnel_services,
    ssh_tunnel_user,
)
from .ssh_tunnel_self_hosted_v2 import provision_ssh_tunnel_self_hosted_v2


async def _probe_key_auth(
    conn,
    *,
    host: str,
    port: int,
    user: str,
    key_path: str,
    known_hosts: str,
) -> tuple[bool, str]:
    """Probe a real SSH public-key login, not just a TCP connect.

    Iran networks can allow TCP/22 and the initial SSH key exchange while the
    authenticated SSH session stalls or is filtered. A TCP socket probe is not
    sufficient for transport selection, so this uses the exact key/user that
    the tunnel service will use.
    """

    command = (
        "timeout 18 /usr/bin/ssh -vv "
        f"-p {int(port)} "
        f"-i {shlex.quote(key_path)} "
        "-o BatchMode=yes "
        "-o PasswordAuthentication=no "
        "-o KbdInteractiveAuthentication=no "
        "-o StrictHostKeyChecking=yes "
        f"-o UserKnownHostsFile={shlex.quote(known_hosts)} "
        "-o ConnectTimeout=8 "
        "-o ConnectionAttempts=1 "
        "-o ServerAliveInterval=4 "
        "-o ServerAliveCountMax=1 "
        f"{shlex.quote(user)}@{shlex.quote(host)} true"
    )

    result = await conn.run(command, check=False, timeout=25)
    text = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    return result.exit_status == 0, text[-5000:]


async def _backhaul_ready(conn, *, service: str, iface: str, peer_ip: str) -> bool:
    result = await conn.run(
        f"""
set -e
systemctl is-active {shlex.quote(service)} >/dev/null
ip link show {shlex.quote(iface)} >/dev/null
ping -c 2 -W 2 -I {shlex.quote(iface)} {shlex.quote(peer_ip)} >/dev/null
""",
        check=False,
        timeout=15,
    )
    return result.exit_status == 0


async def _wait_private_tunnel(
    ci,
    ce,
    *,
    iran_service: str,
    exit_service: str,
    iface: str,
    iran_ip: str,
    exit_ip: str,
) -> tuple[bool, str]:
    last = "not_ready"

    for _ in range(18):
        await asyncio.sleep(2)

        iran_state = await ci.run(
            f"""
set +e
S="$(systemctl is-active {shlex.quote(iran_service)} 2>/dev/null || true)"
ip link show {shlex.quote(iface)} >/dev/null 2>&1; A=$?
ping -I {shlex.quote(iface)} -c 1 -W 2 {shlex.quote(exit_ip)} >/dev/null 2>&1; P=$?
printf 'service=%s iface=%s ping=%s' "$S" "$A" "$P"
""",
            check=False,
            timeout=10,
        )

        exit_state = await ce.run(
            f"""
set +e
S="$(systemctl is-active {shlex.quote(exit_service)} 2>/dev/null || true)"
ip link show {shlex.quote(iface)} >/dev/null 2>&1; A=$?
ping -I {shlex.quote(iface)} -c 1 -W 2 {shlex.quote(iran_ip)} >/dev/null 2>&1; P=$?
printf 'service=%s iface=%s ping=%s' "$S" "$A" "$P"
""",
            check=False,
            timeout=10,
        )

        iran_text = (iran_state.stdout or "").strip()
        exit_text = (exit_state.stdout or "").strip()
        last = f"iran={iran_text} exit={exit_text}"

        if (
            "service=active iface=0 ping=0" in iran_text
            and "service=active iface=0 ping=0" in exit_text
        ):
            return True, last

    return False, last


async def provision_ssh_tunnel_self_hosted_v3(
    tunnel,
    iran,
    exit_node,
    db,
):
    """V3: fully automatic SSH TUN with authenticated Backhaul fallback.

    V2 provisions the complete key/account/systemd runtime. If V2 reports the
    characteristic state where the SSH service stays alive but no tun device is
    created, V3 tests a real key-authenticated SSH session over the Backhaul
    private address. If that works, TwinPanel rewrites only this tunnel's SSH
    service target and verifies the tunnel automatically.

    This addresses networks where TCP/22 and SSH KEX to the public Exit are
    reachable but the authenticated SSH session is filtered/stalled.
    """

    try:
        return await provision_ssh_tunnel_self_hosted_v2(
            tunnel,
            iran,
            exit_node,
            db,
        )
    except Exception as first_exc:
        first_error = str(first_exc)

        # Only take the private-underlay recovery path after the V2 runtime was
        # actually installed and failed verification. Other provisioning errors
        # should remain visible instead of being hidden by a fallback attempt.
        if "ssh_tun_verify_failed" not in first_error:
            raise

        from .routers.provision import ssh_connect_saved

        number = ssh_tunnel_number(tunnel)
        iface = ssh_tunnel_interface(tunnel)
        user = ssh_tunnel_user(tunnel)
        _, iran_addr, exit_addr = ssh_tunnel_addresses(tunnel)
        iran_ip = iran_addr.split("/", 1)[0]
        exit_ip = exit_addr.split("/", 1)[0]
        iran_service, exit_service = ssh_tunnel_services(tunnel)

        key_dir = f"/etc/twinpanel/tp{number}-ssh"
        key_path = f"{key_dir}/id_ed25519"
        known_hosts = f"{key_dir}/known_hosts"
        iran_unit_path = f"/etc/systemd/system/{iran_service}"

        backhaul = ssh_tunnel_backhaul_values(tunnel)
        backhaul_iran_ip = str(backhaul["iran_ip"])
        backhaul_exit_ip = str(backhaul["exit_ip"])
        backhaul_interface = str(backhaul["interface"])
        backhaul_service = str(backhaul["service"])

        ssh_port = int(getattr(exit_node, "ssh_port", 22) or 22)
        public_target = str(exit_node.public_ip or "").strip()

        ci = None
        ce = None

        try:
            ci = await ssh_connect_saved(iran, db)
            ce = await ssh_connect_saved(exit_node, db)

            iran_bh_ok = await _backhaul_ready(
                ci,
                service=backhaul_service,
                iface=backhaul_interface,
                peer_ip=backhaul_exit_ip,
            )
            exit_bh_ok = await _backhaul_ready(
                ce,
                service=backhaul_service,
                iface=backhaul_interface,
                peer_ip=backhaul_iran_ip,
            )

            if not (iran_bh_ok and exit_bh_ok):
                raise RuntimeError(
                    "ssh_tun_v3_backhaul_not_ready | original="
                    + first_error[-2200:]
                )

            public_auth_ok, public_auth_log = await _probe_key_auth(
                ci,
                host=public_target,
                port=ssh_port,
                user=user,
                key_path=key_path,
                known_hosts=known_hosts,
            )

            private_auth_ok, private_auth_log = await _probe_key_auth(
                ci,
                host=backhaul_exit_ip,
                port=ssh_port,
                user=user,
                key_path=key_path,
                known_hosts=known_hosts,
            )

            print(
                "[SSHTunnelSelfHostedV3] "
                f"tunnel={int(tunnel.id)} "
                f"public_auth={public_auth_ok} "
                f"backhaul_auth={private_auth_ok}",
                flush=True,
            )

            if not private_auth_ok:
                raise RuntimeError(
                    "ssh_tun_v3_auth_failed: "
                    f"public_ok={public_auth_ok} private_ok={private_auth_ok} "
                    "| public=" + public_auth_log[-1400:] +
                    " | backhaul=" + private_auth_log[-2200:]
                )

            # The V2 unit is already complete. Change only the target host to
            # the verified Backhaul private address, then let the existing
            # watchers configure tunX on both sides.
            rewrite = await ci.run(
                f"""
python3 - {shlex.quote(iran_unit_path)} {shlex.quote(public_target)} {shlex.quote(backhaul_exit_ip)} <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
old = sys.argv[2]
new = sys.argv[3]
s = p.read_text()
needle = '@' + old
replacement = '@' + new
if needle not in s:
    raise SystemExit('old SSH target not found in unit')
p.write_text(s.replace(needle, replacement))
PY
systemctl daemon-reload
systemctl reset-failed {shlex.quote(iran_service)} >/dev/null 2>&1 || true
systemctl restart {shlex.quote(iran_service)} >/dev/null 2>&1 || true
""",
                check=False,
                timeout=30,
            )

            if rewrite.exit_status != 0:
                text = ((rewrite.stdout or "") + "\n" + (rewrite.stderr or "")).strip()
                raise RuntimeError("ssh_tun_v3_unit_rewrite_failed: " + text[-2200:])

            ok, last = await _wait_private_tunnel(
                ci,
                ce,
                iran_service=iran_service,
                exit_service=exit_service,
                iface=iface,
                iran_ip=iran_ip,
                exit_ip=exit_ip,
            )

            if not ok:
                iran_log = await ci.run(
                    f"journalctl -u {shlex.quote(iran_service)} -n 80 --no-pager 2>&1 || true",
                    check=False,
                    timeout=20,
                )
                raise RuntimeError(
                    "ssh_tun_v3_private_verify_failed: "
                    + last
                    + " | journal="
                    + ((iran_log.stdout or "") + "\n" + (iran_log.stderr or ""))[-3000:]
                )

            return {
                "interface": iface,
                "iran_ip": iran_ip,
                "exit_ip": exit_ip,
                "iran_service": iran_service,
                "exit_service": exit_service,
                "underlay": "backhaul",
                "target": backhaul_exit_ip,
                "verified": True,
                "public_auth_ok": public_auth_ok,
                "backhaul_auth_ok": private_auth_ok,
            }

        finally:
            if ci is not None:
                ci.close()
                await ci.wait_closed()
            if ce is not None:
                ce.close()
                await ce.wait_closed()
