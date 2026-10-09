import asyncio
import os
import re
import socket
import subprocess
from pathlib import Path

import httpx
import psutil


API = __API_LITERAL__
NODE_ID = __NODE_ID__
SECRET = __SECRET_LITERAL__

STATE_DIR = Path("/var/lib/twinpanel-agent")
WG_DIR = STATE_DIR / "wireguard"


# ============================================================
# PROCESS HELPERS
# ============================================================

def run(args, timeout=8):
    try:
        p = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
        return p.returncode, p.stdout.strip()

    except Exception as exc:
        return 255, str(exc)


def active(name):
    c, _ = run([
        "systemctl",
        "is-active",
        "--quiet",
        name,
    ])
    return c == 0


def running_contains(text):
    c, out = run([
        "systemctl",
        "list-units",
        "--type=service",
        "--state=running",
        "--no-legend",
    ])

    return (
        c == 0
        and text.lower() in out.lower()
    )


def wg_ok():
    c, out = run([
        "wg",
        "show",
        "interfaces",
    ])

    return (
        c == 0
        and bool(out.strip())
    )


def protocols():
    return {
        "cisco": active("ocserv"),
        "openvpn": running_contains("openvpn"),
        "wireguard": wg_ok(),
        "l2tp": (
            active("xl2tpd")
            or active("strongswan")
        ),
        "v2ray": (
            active("xray")
            or active("v2ray")
        ),
    }


def payload():
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return {
        "current_users": 0,
        "cpu_percent": round(
            psutil.cpu_percent(interval=0.2),
            2,
        ),
        "memory_percent": round(
            vm.percent,
            2,
        ),
        "disk_percent": round(
            disk.percent,
            2,
        ),
        "hostname": socket.gethostname(),
        "protocols": protocols(),
    }


# ============================================================
# WIREGUARD TUNNEL
# ============================================================

def ensure_keypair(tunnel_id):
    WG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    private_path = WG_DIR / f"{tunnel_id}.key"
    public_path = WG_DIR / f"{tunnel_id}.pub"

    if not private_path.exists():
        c, private_key = run([
            "wg",
            "genkey",
        ])

        if c != 0 or not private_key:
            raise RuntimeError(
                f"wg genkey failed: {private_key}"
            )

        private_path.write_text(
            private_key.strip() + "\n"
        )

        os.chmod(
            private_path,
            0o600,
        )

    private_key = (
        private_path.read_text().strip()
    )

    if not public_path.exists():

        p = subprocess.run(
            ["wg", "pubkey"],
            input=private_key + "\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
            check=False,
        )

        if p.returncode != 0:
            raise RuntimeError(
                f"wg pubkey failed: {p.stdout}"
            )

        public_path.write_text(
            p.stdout.strip() + "\n"
        )

    return public_path.read_text().strip()


def ping_ms(ip):
    # TWINPANEL_WG_HEALTH_RETRY_V44
    #
    # WireGuard may need a short warm-up after endpoint/port
    # synchronization. Do not declare the tunnel dead based
    # on only two lost ICMP packets.

    attempts = (
        [
            "ping",
            "-c", "5",
            "-W", "1",
            "-i", "0.35",
            ip,
        ],
        [
            "ping",
            "-c", "3",
            "-W", "1",
            "-i", "0.35",
            ip,
        ],
    )

    for command in attempts:

        _, out = run(
            command,
            timeout=8,
        )

        match = re.search(
            r"=\s*[\d.]+/([\d.]+)/",
            out,
        )

        if match:
            return int(
                round(
                    float(
                        match.group(1)
                    )
                )
            )

    return None


def tcp_probe(ip, port=443):
    c, _ = run(
        [
            "bash",
            "-lc",
            (
                f"timeout 3 bash -c "
                f"'</dev/tcp/{ip}/{port}'"
            ),
        ],
        timeout=5,
    )

    return c == 0


# TWINPANEL_SSH_TUNNEL_AGENT_V47
def check_ssh_tun(item):
    ifname = str(
        item.get("health_interface")
        or ""
    ).strip()

    peer_ip = str(
        item.get("health_peer_tunnel_ip")
        or ""
    ).strip()

    service = str(
        item.get("health_service")
        or ""
    ).strip()

    if not ifname:
        return False, "ssh_tun_interface_missing", None

    if not peer_ip:
        return False, "ssh_tun_peer_ip_missing", None

    c, out = run(
        [
            "ip",
            "link",
            "show",
            ifname,
        ],
        timeout=5,
    )

    if c != 0:
        return (
            False,
            f"ssh_tun_interface_down: {out}"[:900],
            None,
        )

    if service:
        c, out = run(
            [
                "systemctl",
                "is-active",
                service,
            ],
            timeout=5,
        )

        if c != 0 or out.strip() != "active":
            return (
                False,
                (
                    "ssh_tun_service_inactive: "
                    + service
                    + " "
                    + out.strip()
                )[:900],
                None,
            )

    latency = ping_ms(peer_ip)

    if latency is None:
        return (
            False,
            "ssh_tun_peer_unreachable",
            None,
        )

    return True, None, latency


def configure_wireguard(item):
    """
    نسخه پایدار:
    دیگر هر 12 ثانیه Interface حذف و ساخته نمی‌شود.
    """

    ifname = item["interface"]

    peer_key = item.get(
        "peer_wireguard_public_key"
    )

    if not peer_key:
        return False, "waiting_peer_key"

    local_address = item["local_address"]
    peer_tunnel_ip = item["peer_tunnel_ip"]
    peer_public_ip = item["peer_public_ip"]
    # TWINPANEL_WG_ASYMMETRIC_AGENT_V46
    base_port = int(item["wireguard_port"])

    listen_port = int(
        item.get("wireguard_listen_port")
        or base_port
    )

    peer_port = int(
        item.get("peer_wireguard_port")
        or base_port
    )

    key_file = (
        WG_DIR
        / f"{item['id']}.key"
    )

    # اگر Interface وجود ندارد، بساز.
    c, _ = run([
        "ip",
        "link",
        "show",
        ifname,
    ])

    if c != 0:

        c, out = run([
            "ip",
            "link",
            "add",
            ifname,
            "type",
            "wireguard",
        ])

        if c != 0:
            return (
                False,
                f"ip_link_add: {out}",
            )

    # IP را بدون حذف Interface Sync کن.
    c, out = run([
        "ip",
        "address",
        "replace",
        local_address,
        "dev",
        ifname,
    ])

    if c != 0:
        return (
            False,
            f"ip_address: {out}",
        )

    # Peer قدیمی احتمالی حذف شود.
    c, peers = run([
        "wg",
        "show",
        ifname,
        "peers",
    ])

    if c == 0:
        for old_peer in peers.split():
            if old_peer != peer_key:
                run([
                    "wg",
                    "set",
                    ifname,
                    "peer",
                    old_peer,
                    "remove",
                ])

    c, out = run([
        "wg",
        "set",
        ifname,
        "private-key",
        str(key_file),
        "listen-port",
        str(listen_port),
        "peer",
        peer_key,
        "allowed-ips",
        f"{peer_tunnel_ip}/32",
        "endpoint",
        f"{peer_public_ip}:{peer_port}",
        "persistent-keepalive",
        "20",
    ])

    if c != 0:
        return (
            False,
            f"wg_set: {out}",
        )

    c, out = run([
        "ip",
        "link",
        "set",
        "up",
        "dev",
        ifname,
    ])

    if c != 0:
        return (
            False,
            f"link_up: {out}",
        )

    run([
        "ip",
        "route",
        "replace",
        f"{peer_tunnel_ip}/32",
        "dev",
        ifname,
    ])

    return True, None


# ============================================================
# IPTABLES HELPERS
# ============================================================

def ipt(table, *args):
    cmd = ["iptables"]

    if table:
        cmd += [
            "-t",
            table,
        ]

    cmd += list(args)

    return run(
        cmd,
        timeout=8,
    )


def ensure_chain(table, chain):
    c, _ = ipt(
        table,
        "-N",
        chain,
    )

    # exit 1 یعنی معمولاً Chain از قبل وجود دارد.
    return c in (0, 1)


def ensure_jump(
    table,
    parent,
    child,
):
    c, _ = ipt(
        table,
        "-C",
        parent,
        "-j",
        child,
    )

    if c == 0:
        return

    ipt(
        table,
        "-I",
        parent,
        "1",
        "-j",
        child,
    )


def flush_chain(table, chain):
    ipt(
        table,
        "-F",
        chain,
    )


# TWINPANEL_SAFE_DEFAULT_INTERFACE_V1
def default_interface():
    """
    Resolve the real kernel default-route interface directly.

    Never use bash -lc here. Login-shell banners/profile output
    must never be allowed to become an iptables interface name.
    """

    c, out = run([
        "ip",
        "-o",
        "-4",
        "route",
        "show",
        "default",
    ])

    if c != 0:
        return None

    for line in out.splitlines():
        parts = line.strip().split()

        if "dev" not in parts:
            continue

        index = parts.index("dev")

        if index + 1 >= len(parts):
            continue

        interface = parts[index + 1].strip()

        # Linux IFNAMSIZ is 16 including the trailing NUL.
        if (
            not interface
            or len(interface) > 15
            or not re.fullmatch(
                r"[A-Za-z0-9_.:-]+",
                interface,
            )
        ):
            continue

        check, _ = run([
            "ip",
            "link",
            "show",
            "dev",
            interface,
        ])

        if check == 0:
            return interface

    return None


def expand_transport(value):
    value = str(
        value or ""
    ).lower()

    if value in {
        "tcp+udp",
        "udp+tcp",
    }:
        return [
            "tcp",
            "udp",
        ]

    if value == "tcp":
        return ["tcp"]

    if value == "udp":
        return ["udp"]

    return []


# ============================================================
# AUTO SERVICE ROUTING
# ============================================================

# TWINPANEL_SERVICE_ROUTING_STRICT_V2
def reconcile_service_routing(items):
    try:
        return _reconcile_service_routing_strict(
            items
        )
    except Exception as exc:
        return (
            False,
            str(exc)[:900],
        )


def _reconcile_service_routing_strict(items):

    wan_if = default_interface()

    if not wan_if:
        raise RuntimeError(
            "default_interface_not_found"
        )


    def must_ipt(
        table,
        *args,
    ):
        code, output = ipt(
            table,
            *args,
        )

        if code != 0:
            command = " ".join(
                str(x)
                for x in args
            )

            raise RuntimeError(
                (
                    "iptables_failed "
                    f"table={table} "
                    f"args={command} "
                    f"error={output}"
                )[:900]
            )

        return code, output


    def ensure_chain_strict(
        table,
        chain,
    ):
        code, _ = ipt(
            table,
            "-S",
            chain,
        )

        if code == 0:
            return

        must_ipt(
            table,
            "-N",
            chain,
        )


    def ensure_jump_strict(
        table,
        parent,
        child,
    ):
        code, _ = ipt(
            table,
            "-C",
            parent,
            "-j",
            child,
        )

        if code == 0:
            return

        must_ipt(
            table,
            "-I",
            parent,
            "1",
            "-j",
            child,
        )


    for table, chain in (
        ("nat", "TP_DNAT"),
        ("nat", "TP_SNAT"),
        ("nat", "TP_EGRESS"),
        ("filter", "TP_FWD"),
        ("filter", "TP_EGRESS_FWD"),
        ("mangle", "TP_CISCO_MSS"),
    ):
        ensure_chain_strict(
            table,
            chain,
        )


    for table, parent, child in (
        (
            "nat",
            "PREROUTING",
            "TP_DNAT",
        ),
        (
            "nat",
            "POSTROUTING",
            "TP_SNAT",
        ),
        (
            "nat",
            "POSTROUTING",
            "TP_EGRESS",
        ),
        (
            "filter",
            "FORWARD",
            "TP_FWD",
        ),
        (
            "filter",
            "FORWARD",
            "TP_EGRESS_FWD",
        ),
        (
            "mangle",
            "FORWARD",
            "TP_CISCO_MSS",
        ),
    ):
        ensure_jump_strict(
            table,
            parent,
            child,
        )


    for table, chain in (
        ("nat", "TP_DNAT"),
        ("nat", "TP_SNAT"),
        ("nat", "TP_EGRESS"),
        ("filter", "TP_FWD"),
        ("filter", "TP_EGRESS_FWD"),
        ("mangle", "TP_CISCO_MSS"),
    ):
        must_ipt(
            table,
            "-F",
            chain,
        )


    egress_subnets=set()


    for item in items:

        role=item.get(
            "node_role"
        )

        interface=str(
            item.get(
                "interface"
            )
            or ""
        ).strip()

        local_ip=str(
            item.get(
                "local_address",
                "",
            )
            or ""
        ).split("/")[0].strip()

        exit_ip=str(
            item.get(
                "exit_tunnel_ip"
            )
            or ""
        ).strip()

        routes=(
            item.get(
                "service_routes"
            )
            or []
        )


        if role == "iran":

            if (
                not interface
                or not local_ip
                or not exit_ip
            ):
                if routes:
                    raise RuntimeError(
                        "iran_route_metadata_missing"
                    )

                continue


            # Exit -> Iran -> Internet
            must_ipt(
                "filter",
                "-A",
                "TP_FWD",
                "-i",
                interface,
                "-o",
                wan_if,
                "-s",
                exit_ip,
                "-m",
                "conntrack",
                "--ctstate",
                "ESTABLISHED,RELATED",
                "-j",
                "ACCEPT",
            )


            for route in routes:

                route_protocol=str(
                    route.get(
                        "protocol",
                        "",
                    )
                    or ""
                ).strip().lower()

                transport=str(
                    route.get(
                        "transport",
                        "",
                    )
                    or ""
                ).strip().lower()


                # --------------------------------
                # Raw ESP / IPsec protocol 50
                # --------------------------------
                if transport == "esp":

                    must_ipt(
                        "nat",
                        "-A",
                        "TP_DNAT",
                        "-i",
                        wan_if,
                        "-p",
                        "esp",
                        "-j",
                        "DNAT",
                        "--to-destination",
                        exit_ip,
                    )

                    must_ipt(
                        "nat",
                        "-A",
                        "TP_SNAT",
                        "-o",
                        interface,
                        "-d",
                        exit_ip,
                        "-p",
                        "esp",
                        "-j",
                        "SNAT",
                        "--to-source",
                        local_ip,
                    )

                    must_ipt(
                        "filter",
                        "-A",
                        "TP_FWD",
                        "-i",
                        wan_if,
                        "-o",
                        interface,
                        "-d",
                        exit_ip,
                        "-p",
                        "esp",
                        "-m",
                        "conntrack",
                        "--ctstate",
                        (
                            "NEW,"
                            "ESTABLISHED,"
                            "RELATED"
                        ),
                        "-j",
                        "ACCEPT",
                    )

                    continue


                public_port=str(
                    int(
                        route[
                            "public_port"
                        ]
                    )
                )

                target_port=str(
                    int(
                        route[
                            "target_port"
                        ]
                    )
                )

                protocols=expand_transport(
                    transport
                )

                if not protocols:
                    raise RuntimeError(
                        (
                            "unsupported_service_transport:"
                            f"{transport}"
                        )
                    )


                for proto in protocols:

                    # Cisco CSTP + V2Ray TCP
                    if (
                        route_protocol
                        in {
                            "cisco",
                            "v2ray",
                        }
                        and proto == "tcp"
                    ):

                        must_ipt(
                            "mangle",
                            "-A",
                            "TP_CISCO_MSS",
                            "-o",
                            interface,
                            "-d",
                            exit_ip,
                            "-p",
                            "tcp",
                            "--dport",
                            target_port,
                            "--tcp-flags",
                            "SYN,RST",
                            "SYN",
                            "-j",
                            "TCPMSS",
                            "--set-mss",
                            "1200",
                        )

                        must_ipt(
                            "mangle",
                            "-A",
                            "TP_CISCO_MSS",
                            "-i",
                            interface,
                            "-s",
                            exit_ip,
                            "-p",
                            "tcp",
                            "--sport",
                            target_port,
                            "--tcp-flags",
                            "SYN,RST",
                            "SYN",
                            "-j",
                            "TCPMSS",
                            "--set-mss",
                            "1200",
                        )


                    must_ipt(
                        "nat",
                        "-A",
                        "TP_DNAT",
                        "-i",
                        wan_if,
                        "-p",
                        proto,
                        "--dport",
                        public_port,
                        "-j",
                        "DNAT",
                        "--to-destination",
                        (
                            f"{exit_ip}:"
                            f"{target_port}"
                        ),
                    )

                    must_ipt(
                        "nat",
                        "-A",
                        "TP_SNAT",
                        "-o",
                        interface,
                        "-d",
                        exit_ip,
                        "-p",
                        proto,
                        "--dport",
                        target_port,
                        "-j",
                        "SNAT",
                        "--to-source",
                        local_ip,
                    )

                    must_ipt(
                        "filter",
                        "-A",
                        "TP_FWD",
                        "-i",
                        wan_if,
                        "-o",
                        interface,
                        "-d",
                        exit_ip,
                        "-p",
                        proto,
                        "--dport",
                        target_port,
                        "-m",
                        "conntrack",
                        "--ctstate",
                        (
                            "NEW,"
                            "ESTABLISHED,"
                            "RELATED"
                        ),
                        "-j",
                        "ACCEPT",
                    )


        elif role == "exit":

            for route in routes:

                subnet=route.get(
                    "client_subnet"
                )

                if subnet:
                    egress_subnets.add(
                        subnet
                    )


    for subnet in sorted(
        egress_subnets
    ):

        must_ipt(
            "nat",
            "-A",
            "TP_EGRESS",
            "-s",
            subnet,
            "-o",
            wan_if,
            "-j",
            "MASQUERADE",
        )

        must_ipt(
            "filter",
            "-A",
            "TP_EGRESS_FWD",
            "-s",
            subnet,
            "-o",
            wan_if,
            "-j",
            "ACCEPT",
        )

        must_ipt(
            "filter",
            "-A",
            "TP_EGRESS_FWD",
            "-d",
            subnet,
            "-i",
            wan_if,
            "-m",
            "conntrack",
            "--ctstate",
            "ESTABLISHED,RELATED",
            "-j",
            "ACCEPT",
        )


    return True, None



# ============================================================
# API REPORT
# ============================================================


# TWINPANEL_HTTP_RETRY_V2027
async def http_request_retry(
    client,
    method,
    url,
    *,
    attempts=4,
    **kwargs,
):
    last = None

    for attempt in range(
        1,
        attempts + 1,
    ):
        try:

            response = await client.request(
                method,
                url,
                **kwargs,
            )

            return response

        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.RemoteProtocolError,
        ) as exc:

            last = exc

            if attempt >= attempts:
                raise

            await asyncio.sleep(
                min(
                    0.7 * attempt,
                    2.5,
                )
            )

    raise last


async def report(
    client,
    tunnel_id,
    public_key,
    selected_transport,
    endpoint_reachable,
    tunnel_reachable,
    latency_ms,
    last_error,
):
    r = await http_request_retry(
        client,
        "POST",
        (
            f"{API}/v1/tunnels/"
            f"{tunnel_id}/node/"
            f"{NODE_ID}/report"
        ),
        headers={
            "X-Node-Secret": SECRET,
        },
        json={
            "wireguard_public_key": public_key,
            "selected_transport": selected_transport,
            "endpoint_reachable": endpoint_reachable,
            "tunnel_reachable": tunnel_reachable,
            "latency_ms": latency_ms,
            "last_error": last_error,
        },
    )

    r.raise_for_status()


# ============================================================
# STALE TUNNEL INTERFACE CLEANUP
# ============================================================

def reconcile_tunnel_interfaces(items):
    """
    فقط Interfaceهای مدیریت‌شده TwinPanel با الگوی mwg<number>
    که دیگر در desired وجود ندارند حذف می‌شوند.

    کلیدهای WireGuard حذف نمی‌شوند تا فعال‌سازی مجدد سریع باشد.
    """

    desired = set()

    for item in items:
        ifname = str(
            item.get("interface") or ""
        ).strip()

        if re.fullmatch(r"mwg\d+", ifname):
            desired.add(ifname)

    c, out = run(
        [
            "ip",
            "-o",
            "link",
            "show",
        ],
        timeout=8,
    )

    if c != 0:
        return (
            False,
            f"ip_link_list: {out}",
        )

    existing = set()

    for line in out.splitlines():
        parts = line.split(":", 2)

        if len(parts) < 2:
            continue

        ifname = (
            parts[1]
            .strip()
            .split("@", 1)[0]
        )

        if re.fullmatch(r"mwg\d+", ifname):
            existing.add(ifname)

    stale = sorted(
        existing - desired
    )

    errors = []

    for ifname in stale:
        c, out = run(
            [
                "ip",
                "link",
                "delete",
                ifname,
            ],
            timeout=8,
        )

        if c != 0:
            errors.append(
                f"{ifname}: {out}"
            )
            continue

        print(
            "[TwinPanel] removed stale "
            f"tunnel interface {ifname}",
            flush=True,
        )

    if errors:
        return (
            False,
            "; ".join(errors)[:900],
        )

    return True, None


# ============================================================
# TUNNEL RECONCILE
# ============================================================

async def reconcile_tunnels(client):

    r = await http_request_retry(
        client,
        "GET",
        (
            f"{API}/v1/tunnels/"
            f"node/{NODE_ID}/desired"
        ),
        headers={
            "X-Node-Secret": SECRET,
        },
    )

    r.raise_for_status()

    items = r.json()

    # Service routing حتی اگر Tunnel لیست خالی شود
    # reconcile می‌شود تا Rule قدیمی حذف شود.
    routing_ok, routing_error = (
        reconcile_service_routing(
            items
        )
    )

    if not routing_ok:
        print(
            "[TwinPanel] service routing ERROR: "
            f"{routing_error}",
            flush=True,
        )

    cleanup_ok, cleanup_error = (
        reconcile_tunnel_interfaces(
            items
        )
    )

    if not cleanup_ok:
        print(
            "[TwinPanel] stale tunnel cleanup ERROR: "
            f"{cleanup_error}",
            flush=True,
        )

    for item in items:

        public_key = None
        selected = None

        endpoint_ok = False
        tunnel_ok = False

        latency = None
        last_error = None

        try:

            # TWINPANEL_SSH_TUNNEL_MAIN_V47
            endpoint_ok = False

            candidates = (
                item.get(
                    "transport_candidates"
                )
                or ["wireguard"]
            )

            # TWINPANEL_AGENT_ACTIVE_TRANSPORT_V2027
            managed_candidates = {
                "quic_2027",
                "arq_2027",
                "kcp_2027",
                "tcp_2027",
                "ssh_tun",
                "ssh_relay",
                "backhaul",
            }

            if any(
                name in managed_candidates
                for name in candidates
            ):
                selected = str(
                    item.get("active_transport")
                    or ""
                ).strip().lower()

                if (
                    selected
                    not in managed_candidates
                    or selected
                    not in candidates
                ):
                    selected = next(
                        (
                            name
                            for name in candidates
                            if name
                            in managed_candidates
                        ),
                        "ssh_tun",
                    )

                # check_ssh_tun checks the externally managed
                # interface/service/peer supplied by Desired State.
                # It is valid for SSH Relay and Backhaul as well.
                ok, err, latency = check_ssh_tun(
                    item
                )

                tunnel_ok = ok
                endpoint_ok = ok
                last_error = err

            elif "wireguard" in candidates:

                public_key = ensure_keypair(
                    item["id"]
                )

                ok, err = configure_wireguard(
                    item
                )

                if ok:
                    selected = "wireguard"

                    await asyncio.sleep(
                        0.6
                    )

                    latency = ping_ms(
                        item[
                            "peer_tunnel_ip"
                        ]
                    )

                    tunnel_ok = (
                        latency is not None
                    )

                    endpoint_ok = tunnel_ok

                    if not tunnel_ok:
                        last_error = (
                            "wireguard_peer_unreachable"
                        )

                else:
                    last_error = err

            if selected is None:
                selected = (
                    candidates[0]
                    if candidates
                    else "wireguard"
                )

        except Exception as exc:

            last_error = str(
                exc
            )[:900]

        # TWINPANEL_SERVICE_ROUTING_HEALTH_V1
        # WireGuard may be reachable while service NAT/MSS routing
        # is broken. Propagate that failure to the control plane.
        if not routing_ok:
            routing_message = (
                "service_routing_failed: "
                f"{routing_error or 'unknown'}"
            )

            if last_error:
                if routing_message not in last_error:
                    last_error = (
                        f"{last_error}; "
                        f"{routing_message}"
                    )[:900]
            else:
                last_error = routing_message[:900]

        await report(
            client,
            item["id"],
            public_key,
            selected,
            endpoint_ok,
            tunnel_ok,
            latency,
            last_error,
        )


# ============================================================
# TWINPANEL_AGENT_ORPHAN_SELF_DISABLE_V1
# ============================================================

ORPHAN_404_LIMIT = 5


def self_disable_orphan_agent():
    """
    Node has been removed from TwinPanel.

    Disable and stop this agent without blocking the
    current Python process on systemd.
    """

    print(
        (
            "[TwinPanel] node no longer exists in "
            "control-plane; disabling agent"
        ),
        flush=True,
    )

    try:
        subprocess.Popen(
            [
                "/bin/sh",
                "-c",
                (
                    "systemctl disable "
                    "twinpanel-agent.service "
                    ">/dev/null 2>&1 || true; "
                    "sleep 1; "
                    "systemctl stop "
                    "twinpanel-agent.service "
                    ">/dev/null 2>&1 || true"
                ),
            ],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    except Exception as exc:
        print(
            (
                "[TwinPanel] orphan self-disable "
                f"ERROR: {exc}"
            ),
            flush=True,
        )


# ============================================================
# LOOPS
# ============================================================

async def heartbeat_loop(client):

    consecutive_not_found = 0

    while True:

        try:

            r = await http_request_retry(
                client,
                "POST",
                (
                    f"{API}/v1/nodes/"
                    f"{NODE_ID}/heartbeat"
                ),
                headers={
                    "X-Node-Secret": SECRET,
                },
                json=payload(),
            )

            # TWINPANEL_AGENT_ORPHAN_SELF_DISABLE_V1
            if r.status_code == 404:

                consecutive_not_found += 1

                print(
                    (
                        "[TwinPanel] heartbeat NODE_NOT_FOUND "
                        f"{consecutive_not_found}/"
                        f"{ORPHAN_404_LIMIT}"
                    ),
                    flush=True,
                )

                if (
                    consecutive_not_found
                    >= ORPHAN_404_LIMIT
                ):
                    self_disable_orphan_agent()

                    # Allow detached systemctl command
                    # to start before this process exits.
                    await asyncio.sleep(2)

                    raise SystemExit(
                        "node_removed_from_control_plane"
                    )

            else:
                # Only a real 404 counts as orphan evidence.
                consecutive_not_found = 0

                r.raise_for_status()

                print(
                    "[TwinPanel] heartbeat OK",
                    flush=True,
                )

        except SystemExit:
            raise

        except Exception as exc:

            print(
                (
                    "[TwinPanel] heartbeat ERROR: "
                    f"{exc}"
                ),
                flush=True,
            )

        await asyncio.sleep(
            30
        )


async def tunnel_loop(client):

    while True:

        try:

            await reconcile_tunnels(
                client
            )

        except Exception as exc:

            print(
                (
                    "[TwinPanel] tunnel reconcile "
                    f"ERROR: {exc}"
                ),
                flush=True,
            )

        await asyncio.sleep(
            12
        )


async def main():

    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timeout = httpx.Timeout(
        connect=8.0,
        read=18.0,
        write=12.0,
        pool=8.0,
    )

    limits = httpx.Limits(
        max_connections=8,
        max_keepalive_connections=4,
        keepalive_expiry=20.0,
    )

    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        verify=True,
    ) as client:

        await asyncio.gather(
            heartbeat_loop(client),
            tunnel_loop(client),
        )


if __name__ == "__main__":
    asyncio.run(main())
