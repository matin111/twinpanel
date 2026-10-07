import asyncio
import shlex


# ============================================================
# TWINPANEL GENERIC SSH TUNNEL V1
# ============================================================

def ssh_tunnel_number(tunnel) -> int:
    tunnel_id = int(tunnel.id)

    # Existing production TP27 must remain untouched.
    if tunnel_id == 30:
        return 27

    return tunnel_id


def ssh_tunnel_interface(tunnel) -> str:
    return f"tun{ssh_tunnel_number(tunnel)}"[:15]


# TWINPANEL_SSH_OVER_BACKHAUL_V1
def ssh_tunnel_backhaul_values(
    tunnel,
) -> dict:
    """
    Deterministic Backhaul addressing.

    Keep this formula identical to
    routers.tunnels._backhaul_runtime_values(),
    but keep it local to avoid circular imports.
    """
    tid = int(tunnel.id)
    slot = 10 + (tid % 230)

    return {
        "network": f"10.253.{slot}.0/24",
        "interface": f"bh{tid}",
        "iran_addr": f"10.253.{slot}.1/24",
        "exit_addr": f"10.253.{slot}.2/24",
        "iran_ip": f"10.253.{slot}.1",
        "exit_ip": f"10.253.{slot}.2",
        "service": (
            f"twinpanel-backhaul-{tid}.service"
        ),
    }


async def _ssh_tcp_probe(
    conn,
    host: str,
    port: int,
) -> bool:
    """
    Test TCP reachability from the Iran node itself.
    This is only transport selection; it does not modify
    routing, firewall, or any running tunnel.
    """
    command = f"""python3 - {host!r} {int(port)} <<'PYPROBE'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])

ok = False

for _ in range(2):
    s = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )

    s.settimeout(2.5)

    try:
        s.connect((host, port))
        ok = True
        break
    except OSError:
        pass
    finally:
        s.close()

raise SystemExit(0 if ok else 1)
PYPROBE
"""

    result = await conn.run(
        command,
        check=False,
    )

    return result.exit_status == 0


def ssh_tunnel_user(tunnel) -> str:
    return f"tp{ssh_tunnel_number(tunnel)}"


def ssh_tunnel_services(tunnel) -> tuple[str, str]:
    number = ssh_tunnel_number(tunnel)

    return (
        f"tp{number}-ssh.service",
        f"tp{number}-exit-tun.service",
    )


def ssh_tunnel_addresses(
    tunnel,
) -> tuple[str, str, str]:
    tunnel_id = int(tunnel.id)

    # Existing TP27 addressing.
    if tunnel_id == 30:
        return (
            "10.77.27.0/30",
            "10.77.27.1/30",
            "10.77.27.2/30",
        )

    # Same deterministic /30 allocation used by TwinPanel.
    value = max(tunnel_id, 1)

    second = 64 + (
        (value // 16384) % 64
    )

    third = (
        value // 64
    ) % 256

    block = (
        value % 64
    ) * 4

    return (
        f"10.{second}.{third}.{block}/30",
        f"10.{second}.{third}.{block + 1}/30",
        f"10.{second}.{third}.{block + 2}/30",
    )


def ssh_tunnel_health_meta(
    tunnel,
    node_id: int,
) -> tuple[str | None, str | None]:
    _, iran_addr, exit_addr = (
        ssh_tunnel_addresses(tunnel)
    )

    iran_ip = iran_addr.split("/")[0]
    exit_ip = exit_addr.split("/")[0]

    iran_service, exit_service = (
        ssh_tunnel_services(tunnel)
    )

    if int(node_id) == int(tunnel.iran_node_id):
        return exit_ip, iran_service

    if int(node_id) == int(tunnel.exit_node_id):
        return iran_ip, exit_service

    return None, None


async def _run(
    conn,
    script: str,
    label: str,
) -> str:
    result = await conn.run(
        script,
        check=False,
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

    return (
        result.stdout or ""
    ).strip()


async def verify_ssh_tunnel(
    tunnel,
    iran,
    exit_node,
    db,
):
    from .routers.provision import (
        ssh_connect_saved,
    )

    iface = ssh_tunnel_interface(tunnel)

    _, iran_addr, exit_addr = (
        ssh_tunnel_addresses(tunnel)
    )

    iran_ip = iran_addr.split("/")[0]
    exit_ip = exit_addr.split("/")[0]

    iran_service, exit_service = (
        ssh_tunnel_services(tunnel)
    )

    ci = None
    ce = None

    try:
        ci = await ssh_connect_saved(
            iran,
            db,
        )

        ce = await ssh_connect_saved(
            exit_node,
            db,
        )

        iran_result = await _run(
            ci,
            f"""
set -e
systemctl is-active {shlex.quote(iran_service)}
ip link show {shlex.quote(iface)} >/dev/null
ping -I {shlex.quote(iface)} -c 3 -W 2 {shlex.quote(exit_ip)}
""",
            "iran_verify",
        )

        exit_result = await _run(
            ce,
            f"""
set -e
systemctl is-active {shlex.quote(exit_service)}
ip link show {shlex.quote(iface)} >/dev/null
ping -I {shlex.quote(iface)} -c 3 -W 2 {shlex.quote(iran_ip)}
""",
            "exit_verify",
        )

        return {
            "interface": iface,
            "iran_ip": iran_ip,
            "exit_ip": exit_ip,
            "iran_service": iran_service,
            "exit_service": exit_service,
            "iran_result": iran_result,
            "exit_result": exit_result,
        }

    finally:
        if ci:
            ci.close()
            await ci.wait_closed()

        if ce:
            ce.close()
            await ce.wait_closed()


async def provision_ssh_tunnel(
    tunnel,
    iran,
    exit_node,
    db,
):
    from .routers.provision import (
        ssh_connect_saved,
    )

    number = ssh_tunnel_number(tunnel)
    iface = ssh_tunnel_interface(tunnel)
    user = ssh_tunnel_user(tunnel)

    _, iran_addr, exit_addr = (
        ssh_tunnel_addresses(tunnel)
    )

    iran_ip = iran_addr.split("/")[0]
    exit_ip = exit_addr.split("/")[0]

    iran_service, exit_service = (
        ssh_tunnel_services(tunnel)
    )

    exit_public_ip = str(
        exit_node.public_ip or ""
    ).strip()

    if not exit_public_ip:
        raise RuntimeError(
            "exit_public_ip_missing"
        )

    # Existing TP27 is already provisioned.
    # Never overwrite its working config.
    if int(tunnel.id) == 30:
        ci = None
        ce = None

        try:
            ci = await ssh_connect_saved(
                iran,
                db,
            )

            ce = await ssh_connect_saved(
                exit_node,
                db,
            )

            await _run(
                ce,
                f"""
systemctl is-active {shlex.quote(exit_service)} >/dev/null \
|| systemctl restart {shlex.quote(exit_service)}
""",
                "tp27_exit_service",
            )

            await _run(
                ci,
                f"""
systemctl is-active {shlex.quote(iran_service)} >/dev/null \
|| systemctl restart {shlex.quote(iran_service)}
""",
                "tp27_iran_service",
            )

        finally:
            if ci:
                ci.close()
                await ci.wait_closed()

            if ce:
                ce.close()
                await ce.wait_closed()

        await asyncio.sleep(2)

        return await verify_ssh_tunnel(
            tunnel,
            iran,
            exit_node,
            db,
        )

    key_dir = (
        f"/etc/twinpanel/tp{number}-ssh"
    )

    key_path = (
        f"{key_dir}/id_ed25519"
    )

    known_hosts = (
        f"{key_dir}/known_hosts"
    )

    exit_helper = (
        f"/usr/local/sbin/"
        f"tp{number}-exit-up"
    )

    iran_helper = (
        f"/usr/local/sbin/"
        f"tp{number}-iran-up"
    )

    exit_unit_path = (
        f"/etc/systemd/system/"
        f"{exit_service}"
    )

    iran_unit_path = (
        f"/etc/systemd/system/"
        f"{iran_service}"
    )

    # Current node architecture uses direct SSH/22
    # between Iran and Exit.
    ssh_port = int(
        getattr(
            exit_node,
            "ssh_port",
            22,
        )
        or 22
    )

    ci = None
    ce = None

    try:
        ci = await ssh_connect_saved(
            iran,
            db,
        )

        ce = await ssh_connect_saved(
            exit_node,
            db,
        )

        # ----------------------------------------------------
        # TWINPANEL_SSH_OVER_BACKHAUL_V1
        # Select the SSH control underlay from the Iran node.
        #
        # Priority:
        #   1) Exit public SSH
        #   2) Backhaul private SSH
        #
        # Never silently provision a dead target.
        # ----------------------------------------------------

        backhaul = ssh_tunnel_backhaul_values(
            tunnel
        )

        backhaul_iran_ip = str(
            backhaul["iran_ip"]
        )

        backhaul_exit_ip = str(
            backhaul["exit_ip"]
        )

        backhaul_interface = str(
            backhaul["interface"]
        )

        backhaul_service = str(
            backhaul["service"]
        )

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

systemctl is-active   {shlex.quote(backhaul_service)}   >/dev/null

ip link show   {shlex.quote(backhaul_interface)}   >/dev/null

ip route get   {shlex.quote(backhaul_exit_ip)}   >/dev/null

ping   -c 2   -W 2   -I {shlex.quote(backhaul_interface)}   {shlex.quote(backhaul_exit_ip)}   >/dev/null
""",
                check=False,
            )

            exit_backhaul = await ce.run(
                f"""
set -e

systemctl is-active   {shlex.quote(backhaul_service)}   >/dev/null

ip link show   {shlex.quote(backhaul_interface)}   >/dev/null
""",
                check=False,
            )

            private_ssh_ok = (
                iran_backhaul.exit_status == 0
                and exit_backhaul.exit_status == 0
                and await _ssh_tcp_probe(
                    ci,
                    backhaul_exit_ip,
                    ssh_port,
                )
            )

            if not private_ssh_ok:
                raise RuntimeError(
                    "ssh_underlay_unreachable:"
                    " public_ssh=failed,"
                    " backhaul_ssh=failed"
                )

            ssh_target = backhaul_exit_ip
            ssh_target_mode = "backhaul"

        print(
            "[SSHTunnel] "
            f"tunnel={int(tunnel.id)} "
            f"underlay={ssh_target_mode} "
            f"target={ssh_target}:{ssh_port}",
            flush=True,
        )

        # ----------------------------------------------------
        # Iran: dedicated key
        # ----------------------------------------------------

        public_key = await _run(
            ci,
            f"""
set -e

install -d -m 700 {shlex.quote(key_dir)}

if [ ! -s {shlex.quote(key_path)} ]; then
    ssh-keygen \
      -q \
      -t ed25519 \
      -N '' \
      -f {shlex.quote(key_path)}
fi

chmod 600 {shlex.quote(key_path)}
chmod 644 {shlex.quote(key_path)}.pub

cat {shlex.quote(key_path)}.pub
""",
            "iran_key",
        )

        public_key = (
            public_key
            .strip()
            .splitlines()[-1]
        )

        if not public_key.startswith(
            "ssh-ed25519 "
        ):
            raise RuntimeError(
                "invalid_generated_public_key"
            )

        # ----------------------------------------------------
        # Exit: read real SSH host key over authenticated
        # control connection. No ssh-keyscan TOFU.
        # ----------------------------------------------------

        host_key = await _run(
            ce,
            r"""
set -e

if [ -s /etc/ssh/ssh_host_ed25519_key.pub ]; then
    awk '{print $1 " " $2}' \
      /etc/ssh/ssh_host_ed25519_key.pub
else
    awk '{print $1 " " $2}' \
      /etc/ssh/ssh_host_rsa_key.pub
fi
""",
            "exit_host_key",
        )

        host_key = (
            host_key
            .strip()
            .splitlines()[-1]
        )

        public_host_target = (
            exit_public_ip
            if ssh_port == 22
            else f"[{exit_public_ip}]:{ssh_port}"
        )

        backhaul_host_target = (
            backhaul_exit_ip
            if ssh_port == 22
            else f"[{backhaul_exit_ip}]:{ssh_port}"
        )

        known_lines = (
            f"{public_host_target} {host_key}\\n"
            f"{backhaul_host_target} {host_key}"
        )

        await _run(
            ci,
            f"""
set -e

printf '%s\\n' \
  {shlex.quote(known_lines)} \
  > {shlex.quote(known_hosts)}

chmod 600 {shlex.quote(known_hosts)}
""",
            "iran_known_hosts",
        )

        # ----------------------------------------------------
        # Exit: dedicated restricted account
        # ----------------------------------------------------

        source_ip = str(
            iran.public_ip or ""
        ).strip()

        source_ips = []

        if source_ip:
            source_ips.append(source_ip)

        if (
            backhaul_iran_ip
            and backhaul_iran_ip
            not in source_ips
        ):
            source_ips.append(
                backhaul_iran_ip
            )

        auth_key = public_key

        if source_ips:
            auth_key = (
                'from="'
                + ",".join(source_ips)
                + '" '
                + public_key
            )

        await _run(
            ce,
            f"""
set -e

groupadd -f twinpanel-tun

if ! id -u {shlex.quote(user)} >/dev/null 2>&1; then
    useradd \
      -m \
      -s /bin/bash \
      -g twinpanel-tun \
      {shlex.quote(user)}
fi

usermod \
  -a \
  -G twinpanel-tun \
  {shlex.quote(user)}

# TWINPANEL_SSH_TUN_KEYONLY_ACCOUNT_V2
# Keep the account unlocked for OpenSSH public-key authentication,
# but assign an unknown random password hash.
# PasswordAuthentication remains disabled by the Match rule.
TP_RANDOM_PASSWORD="$(openssl rand -hex 48)"
TP_RANDOM_HASH="$(openssl passwd -6 "$TP_RANDOM_PASSWORD")"
usermod -p "$TP_RANDOM_HASH" {shlex.quote(user)}
unset TP_RANDOM_PASSWORD TP_RANDOM_HASH

install \
  -d \
  -m 700 \
  -o {shlex.quote(user)} \
  -g twinpanel-tun \
  /home/{shlex.quote(user)}/.ssh

printf '%s\\n' \
  {shlex.quote(auth_key)} \
  > /home/{shlex.quote(user)}/.ssh/authorized_keys

chown \
  {shlex.quote(user)}:twinpanel-tun \
  /home/{shlex.quote(user)}/.ssh/authorized_keys

chmod 600 \
  /home/{shlex.quote(user)}/.ssh/authorized_keys

if ! grep -q \
  '^# BEGIN TWINPANEL TUNNEL GROUP$' \
  /etc/ssh/sshd_config
then
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

systemctl reload ssh 2>/dev/null \
|| systemctl reload sshd
""",
            "exit_account",
        )

        # ----------------------------------------------------
        # Exit: persistent TUN device
        # ----------------------------------------------------

        await _run(
            ce,
            f"""
set -e

cat > {shlex.quote(exit_helper)} <<'EOF'
#!/bin/bash
set -e

modprobe tun

if ! ip link show {iface} >/dev/null 2>&1; then
    ip tuntap add \
      dev {iface} \
      mode tun \
      user {user}
fi

ip addr flush dev {iface}

ip addr add \
  {exit_addr} \
  peer {iran_ip} \
  dev {iface}

ip link set \
  dev {iface} \
  mtu 1400 \
  up
EOF

chmod 755 {shlex.quote(exit_helper)}

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
""",
            "exit_tun_service",
        )

        # ----------------------------------------------------
        # Iran: SSH TUN systemd service
        # ----------------------------------------------------

        await _run(
            ci,
            f"""
set -e

cat > {shlex.quote(iran_helper)} <<'EOF'
#!/bin/bash
set -e

for i in $(seq 1 20); do
    if ip link show {iface} >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

ip link show {iface} >/dev/null 2>&1

ip addr flush dev {iface}

ip addr add \
  {iran_addr} \
  peer {exit_ip} \
  dev {iface}

ip link set \
  dev {iface} \
  mtu 1400 \
  up
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

systemctl enable \
  {shlex.quote(iran_service)} \
  >/dev/null

systemctl restart \
  {shlex.quote(iran_service)}
""",
            "iran_ssh_service",
        )

        await asyncio.sleep(4)

    finally:
        if ci:
            ci.close()
            await ci.wait_closed()

        if ce:
            ce.close()
            await ce.wait_closed()

    return await verify_ssh_tunnel(
        tunnel,
        iran,
        exit_node,
        db,
    )


async def cleanup_ssh_tunnel(
    tunnel,
    iran,
    exit_node,
    db,
):
    # Never automatically remove existing production TP27.
    if int(tunnel.id) == 30:
        return

    from .routers.provision import (
        ssh_connect_saved,
    )

    number = ssh_tunnel_number(tunnel)
    iface = ssh_tunnel_interface(tunnel)
    user = ssh_tunnel_user(tunnel)

    iran_service, exit_service = (
        ssh_tunnel_services(tunnel)
    )

    key_dir = f"/etc/twinpanel/tp{number}-ssh"

    ci = None
    ce = None

    try:
        try:
            ci = await ssh_connect_saved(
                iran,
                db,
            )

            await ci.run(
                f"""
systemctl disable --now {shlex.quote(iran_service)} >/dev/null 2>&1 || true
rm -f /etc/systemd/system/{shlex.quote(iran_service)}
rm -f /usr/local/sbin/tp{number}-iran-up
ip link del {shlex.quote(iface)} >/dev/null 2>&1 || true
rm -rf {shlex.quote(key_dir)}
systemctl daemon-reload
""",
                check=False,
            )

        except Exception:
            pass

        try:
            ce = await ssh_connect_saved(
                exit_node,
                db,
            )

            await ce.run(
                f"""
systemctl disable --now {shlex.quote(exit_service)} >/dev/null 2>&1 || true
rm -f /etc/systemd/system/{shlex.quote(exit_service)}
rm -f /usr/local/sbin/tp{number}-exit-up
ip link del {shlex.quote(iface)} >/dev/null 2>&1 || true
userdel -r {shlex.quote(user)} >/dev/null 2>&1 || true
systemctl daemon-reload
""",
                check=False,
            )

        except Exception:
            pass

    finally:
        if ci:
            ci.close()
            await ci.wait_closed()

        if ce:
            ce.close()
            await ce.wait_closed()
