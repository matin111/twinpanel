from __future__ import annotations

import asyncio
import shlex

from .ssh_tunnel import (
    _run,
    _ssh_tcp_probe,
    provision_ssh_tunnel as _legacy_provision_ssh_tunnel,
    ssh_tunnel_addresses,
    ssh_tunnel_backhaul_values,
    ssh_tunnel_interface,
    ssh_tunnel_number,
    ssh_tunnel_services,
    ssh_tunnel_user,
)


async def _diag(conn, service: str, iface: str) -> str:
    result = await conn.run(
        f"""
set +e
printf '%s\n' '=== service ==='
systemctl status {shlex.quote(service)} --no-pager -l 2>&1
printf '%s\n' '=== journal ==='
journalctl -u {shlex.quote(service)} -n 60 --no-pager 2>&1
printf '%s\n' '=== interface ==='
ip -details addr show dev {shlex.quote(iface)} 2>&1
printf '%s\n' '=== tun ==='
ls -l /dev/net/tun 2>&1
""",
        check=False,
    )
    return ((result.stdout or "") + "\n" + (result.stderr or ""))[-5000:]


async def provision_ssh_tunnel_self_hosted(
    tunnel,
    iran,
    exit_node,
    db,
):
    """Provision SSH TUN completely from TwinPanel.

    The historical implementation pre-created the remote tunX interface before
    OpenSSH started with ``-w X:X``. OpenSSH itself owns creation of that TUN
    device, so the pre-created interface can make tunnel forwarding fail. This
    self-hosted implementation lets sshd create the interface and keeps a small
    root watcher on the Exit node which configures the address whenever the TUN
    appears or is recreated after an SSH reconnect.

    No manual changes on either node are required. The controller performs all
    preparation, cleanup, service installation, verification and diagnostics
    through the node credentials already stored in TwinPanel.
    """

    # Preserve the explicitly protected legacy production tunnel unchanged.
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

    exit_public_ip = str(exit_node.public_ip or "").strip()
    if not exit_public_ip:
        raise RuntimeError("exit_public_ip_missing")

    key_dir = f"/etc/twinpanel/tp{number}-ssh"
    key_path = f"{key_dir}/id_ed25519"
    known_hosts = f"{key_dir}/known_hosts"

    exit_helper = f"/usr/local/sbin/tp{number}-exit-up"
    iran_helper = f"/usr/local/sbin/tp{number}-iran-up"
    exit_unit_path = f"/etc/systemd/system/{exit_service}"
    iran_unit_path = f"/etc/systemd/system/{iran_service}"

    ssh_port = int(getattr(exit_node, "ssh_port", 22) or 22)

    ci = None
    ce = None

    try:
        ci = await ssh_connect_saved(iran, db)
        ce = await ssh_connect_saved(exit_node, db)

        # The node bootstrap already installs the normal runtime. Here we only
        # validate the kernel/OpenSSH prerequisites and load TUN automatically.
        await _run(
            ci,
            """
set -e
modprobe tun >/dev/null 2>&1 || true
test -c /dev/net/tun
command -v ssh >/dev/null
command -v ip >/dev/null
""",
            "iran_prerequisites",
        )

        await _run(
            ce,
            """
set -e
modprobe tun >/dev/null 2>&1 || true
test -c /dev/net/tun
command -v sshd >/dev/null || test -x /usr/sbin/sshd
command -v ip >/dev/null
""",
            "exit_prerequisites",
        )

        backhaul = ssh_tunnel_backhaul_values(tunnel)
        backhaul_iran_ip = str(backhaul["iran_ip"])
        backhaul_exit_ip = str(backhaul["exit_ip"])
        backhaul_interface = str(backhaul["interface"])
        backhaul_service = str(backhaul["service"])

        public_ssh_ok = await _ssh_tcp_probe(
            ci,
            exit_public_ip,
            ssh_port,
        )

        ssh_target = exit_public_ip
        ssh_target_mode = "public"

        if not public_ssh_ok:
            iran_backhaul = await ci.run(
                f"""
set -e
systemctl is-active {shlex.quote(backhaul_service)} >/dev/null
ip link show {shlex.quote(backhaul_interface)} >/dev/null
ip route get {shlex.quote(backhaul_exit_ip)} >/dev/null
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
            "[SSHTunnelSelfHosted] "
            f"tunnel={int(tunnel.id)} "
            f"underlay={ssh_target_mode} "
            f"target={ssh_target}:{ssh_port}",
            flush=True,
        )

        # Stop only this tunnel's previous runtime before replacing it. This is
        # what makes panel-side reinstall/repair idempotent.
        await ci.run(
            f"""
set +e
systemctl stop {shlex.quote(iran_service)} >/dev/null 2>&1
ip link delete {shlex.quote(iface)} >/dev/null 2>&1
true
""",
            check=False,
        )

        await ce.run(
            f"""
set +e
systemctl stop {shlex.quote(exit_service)} >/dev/null 2>&1
ip link delete {shlex.quote(iface)} >/dev/null 2>&1
true
""",
            check=False,
        )

        # Iran: dedicated client key.
        public_key = await _run(
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

        # Exit: trust the authenticated host key, not TOFU ssh-keyscan.
        host_key = await _run(
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
        known_lines = (
            f"{public_host_target} {host_key}\\n"
            f"{backhaul_host_target} {host_key}"
        )

        await _run(
            ci,
            f"""
set -e
printf '%s\\n' {shlex.quote(known_lines)} > {shlex.quote(known_hosts)}
chmod 600 {shlex.quote(known_hosts)}
""",
            "iran_known_hosts",
        )

        # Exit: dedicated restricted key-only account with PermitTunnel.
        source_ip = str(iran.public_ip or "").strip()
        source_ips: list[str] = []
        if source_ip:
            source_ips.append(source_ip)
        if backhaul_iran_ip and backhaul_iran_ip not in source_ips:
            source_ips.append(backhaul_iran_ip)

        auth_key = public_key
        if source_ips:
            auth_key = 'from="' + ",".join(source_ips) + '" ' + public_key

        await _run(
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
printf '%s\\n' {shlex.quote(auth_key)} > /home/{shlex.quote(user)}/.ssh/authorized_keys
chown {shlex.quote(user)}:twinpanel-tun /home/{shlex.quote(user)}/.ssh/authorized_keys
chmod 600 /home/{shlex.quote(user)}/.ssh/authorized_keys

if ! grep -q '^# BEGIN TWINPANEL TUNNEL GROUP$' /etc/ssh/sshd_config; then
cat >> /etc/ssh/sshd_config <<'EOF'

# BEGIN TWINPANEL TUNNEL GROUP
Match Group twinpanel-tun
    PermitTunnel point-to-point
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
""",
            "exit_account",
        )

        # Exit: do NOT pre-create tunX. sshd creates the requested device for
        # -w X:X. This watcher configures it each time it appears/reappears.
        await _run(
            ce,
            f"""
set -e
cat > {shlex.quote(exit_helper)} <<'EOF'
#!/bin/bash
set -u
modprobe tun >/dev/null 2>&1 || true

while true; do
    while ! ip link show {iface} >/dev/null 2>&1; do
        sleep 1
    done

    ip addr flush dev {iface} >/dev/null 2>&1 || true
    ip addr add {exit_addr} peer {iran_ip} dev {iface}
    ip link set dev {iface} mtu 1400 up

    while ip link show {iface} >/dev/null 2>&1; do
        sleep 2
    done

done
EOF
chmod 755 {shlex.quote(exit_helper)}

cat > {shlex.quote(exit_unit_path)} <<'EOF'
[Unit]
Description=TwinPanel SSH Tunnel Exit Watcher {number}
Wants=network-online.target
After=network-online.target ssh.service sshd.service

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

        # Iran: OpenSSH owns local tunX creation. ExecStartPost configures the
        # local address on every systemd restart/reconnect.
        await _run(
            ci,
            f"""
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
chmod 755 {shlex.quote(iran_helper)}

cat > {shlex.quote(iran_unit_path)} <<'EOF'
[Unit]
Description=TwinPanel SSH Tunnel {number}
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart=/usr/bin/ssh -p {ssh_port} -i {key_path} -o BatchMode=yes -o PasswordAuthentication=no -o StrictHostKeyChecking=yes -o UserKnownHostsFile={known_hosts} -o Tunnel=point-to-point -o ExitOnForwardFailure=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 -o ServerAliveInterval=5 -o ServerAliveCountMax=3 -o TCPKeepAlive=yes -o Compression=no -o IPQoS=none -w {number}:{number} -N {user}@{ssh_target}
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
""",
            "iran_ssh_service",
        )

        # Panel-owned verification with bounded retry. If it fails, return the
        # actual service journals to the API so the UI can show a useful reason
        # without asking the operator to SSH into either node.
        last_state = "ssh_tun_not_ready"

        for _ in range(20):
            await asyncio.sleep(2)

            iran_state = await ci.run(
                f"""
set +e
systemctl is-active {shlex.quote(iran_service)}
ip link show {shlex.quote(iface)} >/dev/null 2>&1
A=$?
ping -I {shlex.quote(iface)} -c 1 -W 2 {shlex.quote(exit_ip)} >/dev/null 2>&1
P=$?
printf 'iface=%s ping=%s' "$A" "$P"
""",
                check=False,
            )

            exit_state = await ce.run(
                f"""
set +e
systemctl is-active {shlex.quote(exit_service)}
ip link show {shlex.quote(iface)} >/dev/null 2>&1
A=$?
ping -I {shlex.quote(iface)} -c 1 -W 2 {shlex.quote(iran_ip)} >/dev/null 2>&1
P=$?
printf 'iface=%s ping=%s' "$A" "$P"
""",
                check=False,
            )

            iran_text = (iran_state.stdout or "").strip()
            exit_text = (exit_state.stdout or "").strip()
            last_state = f"iran={iran_text} exit={exit_text}"

            if (
                iran_state.exit_status == 0
                and exit_state.exit_status == 0
                and iran_text.startswith("active")
                and "iface=0 ping=0" in iran_text
                and exit_text.startswith("active")
                and "iface=0 ping=0" in exit_text
            ):
                return {
                    "interface": iface,
                    "iran_ip": iran_ip,
                    "exit_ip": exit_ip,
                    "iran_service": iran_service,
                    "exit_service": exit_service,
                    "underlay": ssh_target_mode,
                    "target": ssh_target,
                    "verified": True,
                }

        iran_diag = await _diag(ci, iran_service, iface)
        exit_diag = await _diag(ce, exit_service, iface)

        raise RuntimeError(
            "ssh_tun_verify_failed: "
            + last_state
            + " | iran_diag="
            + iran_diag[-1800:]
            + " | exit_diag="
            + exit_diag[-1800:]
        )

    finally:
        if ci:
            ci.close()
            await ci.wait_closed()
        if ce:
            ce.close()
            await ce.wait_closed()
