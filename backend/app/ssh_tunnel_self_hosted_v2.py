from __future__ import annotations

import asyncio
import shlex

from .ssh_tunnel import (
    _ssh_tcp_probe,
    provision_ssh_tunnel as _legacy_provision_ssh_tunnel,
    ssh_tunnel_addresses,
    ssh_tunnel_backhaul_values,
    ssh_tunnel_interface,
    ssh_tunnel_number,
    ssh_tunnel_services,
    ssh_tunnel_user,
)


async def _run_checked(conn, script: str, label: str, *, timeout: int = 90) -> str:
    result = await conn.run(script, check=False, timeout=timeout)
    if result.exit_status != 0:
        text = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        raise RuntimeError(f"{label}: {text[-3500:] or 'command_failed'}")
    return (result.stdout or "").strip()


async def _collect_diag(
    conn,
    *,
    service: str,
    watcher: str | None,
    iface: str,
    user: str | None = None,
    source_ip: str | None = None,
) -> str:
    watcher_part = ""
    if watcher:
        watcher_part = f"""
printf '%s\n' '=== watcher status ==='
systemctl status {shlex.quote(watcher)} --no-pager -l 2>&1 || true
printf '%s\n' '=== watcher journal ==='
journalctl -u {shlex.quote(watcher)} -n 50 --no-pager 2>&1 || true
"""

    sshd_part = ""
    if user:
        addr = source_ip or "127.0.0.1"
        sshd_part = f"""
printf '%s\n' '=== sshd effective config ==='
/usr/sbin/sshd -T -C user={shlex.quote(user)},host=localhost,addr={shlex.quote(addr)} 2>&1 \
  | grep -E '^(permittunnel|passwordauthentication|kbdinteractiveauthentication|allowtcpforwarding|permittty) ' \
  || true
"""

    result = await conn.run(
        f"""
set +e
printf '%s\n' '=== service status ==='
systemctl status {shlex.quote(service)} --no-pager -l 2>&1 || true
printf '%s\n' '=== service journal ==='
journalctl -u {shlex.quote(service)} -n 90 --no-pager 2>&1 || true
{watcher_part}
printf '%s\n' '=== interface ==='
ip -details addr show dev {shlex.quote(iface)} 2>&1 || true
printf '%s\n' '=== tun device ==='
ls -l /dev/net/tun 2>&1 || true
{sshd_part}
""",
        check=False,
        timeout=45,
    )
    return ((result.stdout or "") + "\n" + (result.stderr or ""))[-7000:]


async def provision_ssh_tunnel_self_hosted_v2(
    tunnel,
    iran,
    exit_node,
    db,
):
    """Provision/repair SSH TUN entirely from TwinPanel.

    Design goals:
      * no manual node changes;
      * no pre-created TUN device before OpenSSH -w;
      * NAT-safe key authentication (no fragile authorized_keys from= filter);
      * dedicated address watchers instead of blocking ExecStartPost;
      * bounded verification and controller-side diagnostics.
    """

    # Preserve the protected historical production tunnel exactly as-is.
    if int(tunnel.id) == 30:
        return await _legacy_provision_ssh_tunnel(
            tunnel,
            iran,
            exit_node,
            db,
        )

    from .routers.provision import ssh_connect_saved

    number = ssh_tunnel_number(tunnel)
    iface = ssh_tunnel_interface(tunnel)
    user = ssh_tunnel_user(tunnel)
    _, iran_addr, exit_addr = ssh_tunnel_addresses(tunnel)
    iran_ip = iran_addr.split("/", 1)[0]
    exit_ip = exit_addr.split("/", 1)[0]
    iran_service, exit_service = ssh_tunnel_services(tunnel)

    iran_watcher = f"tp{number}-iran-tun.service"

    exit_public_ip = str(exit_node.public_ip or "").strip()
    if not exit_public_ip:
        raise RuntimeError("exit_public_ip_missing")

    ssh_port = int(getattr(exit_node, "ssh_port", 22) or 22)

    key_dir = f"/etc/twinpanel/tp{number}-ssh"
    key_path = f"{key_dir}/id_ed25519"
    known_hosts = f"{key_dir}/known_hosts"

    iran_helper = f"/usr/local/sbin/tp{number}-iran-up"
    exit_helper = f"/usr/local/sbin/tp{number}-exit-up"

    iran_unit_path = f"/etc/systemd/system/{iran_service}"
    iran_watcher_path = f"/etc/systemd/system/{iran_watcher}"
    exit_unit_path = f"/etc/systemd/system/{exit_service}"

    ci = None
    ce = None

    try:
        ci = await ssh_connect_saved(iran, db)
        ce = await ssh_connect_saved(exit_node, db)

        # Panel-owned prerequisite repair.
        await _run_checked(
            ci,
            """
set -e
modprobe tun >/dev/null 2>&1 || true
test -c /dev/net/tun
command -v ssh >/dev/null
command -v ssh-keygen >/dev/null
command -v ip >/dev/null
""",
            "iran_prerequisites",
        )
        await _run_checked(
            ce,
            """
set -e
modprobe tun >/dev/null 2>&1 || true
test -c /dev/net/tun
test -x /usr/sbin/sshd
command -v ip >/dev/null
command -v openssl >/dev/null
""",
            "exit_prerequisites",
        )

        # Select public SSH first, Backhaul private SSH second.
        backhaul = ssh_tunnel_backhaul_values(tunnel)
        backhaul_iran_ip = str(backhaul["iran_ip"])
        backhaul_exit_ip = str(backhaul["exit_ip"])
        backhaul_interface = str(backhaul["interface"])
        backhaul_service = str(backhaul["service"])

        public_ssh_ok = await _ssh_tcp_probe(ci, exit_public_ip, ssh_port)
        ssh_target = exit_public_ip
        ssh_target_mode = "public"

        if not public_ssh_ok:
            iran_backhaul = await ci.run(
                f"""
set -e
systemctl is-active {shlex.quote(backhaul_service)} >/dev/null
ip link show {shlex.quote(backhaul_interface)} >/dev/null
ping -c 2 -W 2 -I {shlex.quote(backhaul_interface)} {shlex.quote(backhaul_exit_ip)} >/dev/null
""",
                check=False,
            )
            exit_backhaul = await ce.run(
                f"""
set -e
systemctl is-active {shlex.quote(backhaul_service)} >/dev/null
ip link show {shlex.quote(backhaul_interface)} >/dev/null
""",
                check=False,
            )
            private_ssh_ok = (
                iran_backhaul.exit_status == 0
                and exit_backhaul.exit_status == 0
                and await _ssh_tcp_probe(ci, backhaul_exit_ip, ssh_port)
            )
            if not private_ssh_ok:
                raise RuntimeError(
                    "ssh_underlay_unreachable: public_ssh=failed, backhaul_ssh=failed"
                )
            ssh_target = backhaul_exit_ip
            ssh_target_mode = "backhaul"

        print(
            "[SSHTunnelSelfHostedV2] "
            f"tunnel={int(tunnel.id)} "
            f"underlay={ssh_target_mode} "
            f"target={ssh_target}:{ssh_port}",
            flush=True,
        )

        # Stop only this tunnel's old runtime. The panel owns the reinstall.
        await ci.run(
            f"""
set +e
systemctl disable --now {shlex.quote(iran_service)} >/dev/null 2>&1
systemctl disable --now {shlex.quote(iran_watcher)} >/dev/null 2>&1
ip link delete {shlex.quote(iface)} >/dev/null 2>&1
true
""",
            check=False,
        )
        await ce.run(
            f"""
set +e
systemctl disable --now {shlex.quote(exit_service)} >/dev/null 2>&1
ip link delete {shlex.quote(iface)} >/dev/null 2>&1
true
""",
            check=False,
        )

        # Dedicated Iran client key.
        public_key = await _run_checked(
            ci,
            f"""
set -e
install -d -m 700 {shlex.quote(key_dir)}
if [ ! -s {shlex.quote(key_path)} ]; then
    ssh-keygen -q -t ed25519 -N '' -f {shlex.quote(key_path)}
fi
chmod 600 {shlex.quote(key_path)}
chmod 644 {shlex.quote(key_path)}.pub
cat {shlex.quote(key_path)}.pub
""",
            "iran_key",
        )
        public_key = public_key.strip().splitlines()[-1]
        if not public_key.startswith("ssh-ed25519 "):
            raise RuntimeError("invalid_generated_public_key")

        # Read the authenticated Exit host key and write proper separate
        # known_hosts lines for both possible underlays.
        host_key = await _run_checked(
            ce,
            r"""
set -e
if [ -s /etc/ssh/ssh_host_ed25519_key.pub ]; then
    awk '{print $1 " " $2}' /etc/ssh/ssh_host_ed25519_key.pub
else
    awk '{print $1 " " $2}' /etc/ssh/ssh_host_rsa_key.pub
fi
""",
            "exit_host_key",
        )
        host_key = host_key.strip().splitlines()[-1]

        public_host_target = (
            exit_public_ip if ssh_port == 22 else f"[{exit_public_ip}]:{ssh_port}"
        )
        backhaul_host_target = (
            backhaul_exit_ip if ssh_port == 22 else f"[{backhaul_exit_ip}]:{ssh_port}"
        )
        public_known_line = f"{public_host_target} {host_key}"
        backhaul_known_line = f"{backhaul_host_target} {host_key}"

        await _run_checked(
            ci,
            f"""
set -e
printf '%s\\n%s\\n' \
  {shlex.quote(public_known_line)} \
  {shlex.quote(backhaul_known_line)} \
  > {shlex.quote(known_hosts)}
chmod 600 {shlex.quote(known_hosts)}
""",
            "iran_known_hosts",
        )

        # Dedicated key-only account. Do not bind authorized_keys to a guessed
        # source address: NAT/carrier/provider routing can change the source IP.
        # The account remains locked down by Match User and the unique key.
        match_begin = f"# BEGIN TWINPANEL SSH TUN USER {user}"
        match_end = f"# END TWINPANEL SSH TUN USER {user}"

        await _run_checked(
            ce,
            f"""
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
install -d -m 700 -o {shlex.quote(user)} -g twinpanel-tun /home/{shlex.quote(user)}/.ssh
printf '%s\\n' {shlex.quote(public_key)} > /home/{shlex.quote(user)}/.ssh/authorized_keys
chown {shlex.quote(user)}:twinpanel-tun /home/{shlex.quote(user)}/.ssh/authorized_keys
chmod 600 /home/{shlex.quote(user)}/.ssh/authorized_keys

python3 - <<'PYCONF'
from pathlib import Path
p = Path('/etc/ssh/sshd_config')
s = p.read_text()
begin = {match_begin!r}
end = {match_end!r}
block = '''{match_begin}
Match User {user}
    PermitTunnel point-to-point
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    AllowTcpForwarding no
    AllowAgentForwarding no
    X11Forwarding no
    PermitTTY no
    PermitUserRC no
{match_end}
'''
if begin in s and end in s:
    before, tail = s.split(begin, 1)
    _, after = tail.split(end, 1)
    s = before.rstrip() + '\\n\\n' + block + after.lstrip('\\n')
else:
    s = s.rstrip() + '\\n\\n' + block
p.write_text(s)
PYCONF

/usr/sbin/sshd -t
systemctl reload ssh 2>/dev/null || systemctl reload sshd

EFFECTIVE="$(/usr/sbin/sshd -T -C user={shlex.quote(user)},host=localhost,addr=127.0.0.1 | awk '$1=="permittunnel" {{print $2}}')"
case "$EFFECTIVE" in
  yes|point-to-point) ;;
  *) echo "PermitTunnel effective value is: $EFFECTIVE" >&2; exit 44 ;;
esac
""",
            "exit_account_and_sshd",
        )

        # Exit watcher: sshd creates tunX, watcher only assigns address/MTU.
        await _run_checked(
            ce,
            f"""
set -e
cat > {shlex.quote(exit_helper)} <<'EOF'
#!/bin/bash
set -u
modprobe tun >/dev/null 2>&1 || true
while true; do
    while ! ip link show {iface} >/dev/null 2>&1; do sleep 1; done
    ip addr flush dev {iface} >/dev/null 2>&1 || true
    ip addr add {exit_addr} peer {iran_ip} dev {iface} || true
    ip link set dev {iface} mtu 1400 up || true
    while ip link show {iface} >/dev/null 2>&1; do sleep 2; done
done
EOF
chmod 755 {shlex.quote(exit_helper)}
cat > {shlex.quote(exit_unit_path)} <<'EOF'
[Unit]
Description=TwinPanel SSH Tunnel Exit Watcher {number}
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart={exit_helper}
Restart=always
RestartSec=2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable {shlex.quote(exit_service)} >/dev/null
systemctl restart {shlex.quote(exit_service)}
""",
            "exit_tun_watcher",
        )

        # Iran address watcher is separate from the SSH service. This avoids a
        # blocking ExecStartPost turning a healthy/retrying SSH process into a
        # failed systemd start transaction.
        await _run_checked(
            ci,
            f"""
set -e
cat > {shlex.quote(iran_helper)} <<'EOF'
#!/bin/bash
set -u
modprobe tun >/dev/null 2>&1 || true
while true; do
    while ! ip link show {iface} >/dev/null 2>&1; do sleep 1; done
    ip addr flush dev {iface} >/dev/null 2>&1 || true
    ip addr add {iran_addr} peer {exit_ip} dev {iface} || true
    ip link set dev {iface} mtu 1400 up || true
    while ip link show {iface} >/dev/null 2>&1; do sleep 2; done
done
EOF
chmod 755 {shlex.quote(iran_helper)}
cat > {shlex.quote(iran_watcher_path)} <<'EOF'
[Unit]
Description=TwinPanel SSH Tunnel Iran Watcher {number}
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart={iran_helper}
Restart=always
RestartSec=2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

cat > {shlex.quote(iran_unit_path)} <<'EOF'
[Unit]
Description=TwinPanel SSH Tunnel {number}
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart=/usr/bin/ssh -v -p {ssh_port} -i {key_path} -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o StrictHostKeyChecking=yes -o UserKnownHostsFile={known_hosts} -o Tunnel=point-to-point -o ExitOnForwardFailure=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 -o ServerAliveInterval=5 -o ServerAliveCountMax=3 -o TCPKeepAlive=yes -o Compression=no -o IPQoS=none -w {number}:{number} -N {user}@{ssh_target}
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable {shlex.quote(iran_watcher)} {shlex.quote(iran_service)} >/dev/null
systemctl restart {shlex.quote(iran_watcher)}
systemctl reset-failed {shlex.quote(iran_service)} >/dev/null 2>&1 || true
systemctl restart {shlex.quote(iran_service)} >/dev/null 2>&1 || true
""",
            "iran_services_install",
        )

        last_state = "not_ready"
        restarted_once = False

        for attempt in range(24):
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
            )

            iran_text = (iran_state.stdout or "").strip()
            exit_text = (exit_state.stdout or "").strip()
            last_state = f"iran={iran_text} exit={exit_text}"

            if (
                "service=active iface=0 ping=0" in iran_text
                and "service=active iface=0 ping=0" in exit_text
            ):
                return {
                    "interface": iface,
                    "iran_ip": iran_ip,
                    "exit_ip": exit_ip,
                    "iran_service": iran_service,
                    "iran_watcher": iran_watcher,
                    "exit_service": exit_service,
                    "underlay": ssh_target_mode,
                    "target": ssh_target,
                    "verified": True,
                }

            # One controller-owned repair retry after the first few probes.
            if attempt >= 4 and not restarted_once and "service=active" not in iran_text:
                restarted_once = True
                await ci.run(
                    f"""
set +e
systemctl reset-failed {shlex.quote(iran_service)} >/dev/null 2>&1
systemctl restart {shlex.quote(iran_watcher)} >/dev/null 2>&1
systemctl restart {shlex.quote(iran_service)} >/dev/null 2>&1
true
""",
                    check=False,
                )

        iran_diag = await _collect_diag(
            ci,
            service=iran_service,
            watcher=iran_watcher,
            iface=iface,
        )
        exit_diag = await _collect_diag(
            ce,
            service=exit_service,
            watcher=None,
            iface=iface,
            user=user,
            source_ip=str(iran.public_ip or "127.0.0.1"),
        )

        raise RuntimeError(
            "ssh_tun_verify_failed: "
            + last_state
            + " | iran_diag="
            + iran_diag[-2600:]
            + " | exit_diag="
            + exit_diag[-2600:]
        )

    finally:
        if ci is not None:
            ci.close()
            await ci.wait_closed()
        if ce is not None:
            ce.close()
            await ce.wait_closed()
