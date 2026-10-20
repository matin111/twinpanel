from __future__ import annotations

import asyncio
import hashlib

from .database import SessionLocal
from .models import Node, NodeType
from .routers.provision import ssh_connect_saved


# ============================================================
# TWINPANEL VPN ACCESS PERFORMANCE V51
#
# Production evidence on the unified GRE path showed a healthy 1360-byte
# Iran<->Exit carrier while ocserv still negotiated Link MTU 1500 / DTLS MTU
# 1434 and then fell back to TLS (no-dtls). V47 already described a 1200-byte
# access-MTU policy, but it gated reconciliation on NodeProtocolConfig.status.
# A stale protocol status could therefore leave a perfectly running service at
# its legacy MTU forever.
#
# V51 makes MTU convergence an Exit-node invariant instead of a dashboard-
# status side effect. Every non-retired Exit is reconciled. Missing protocol
# files/interfaces are simply ignored, so this remains safe for partial nodes.
# Persistent config and live interfaces are verified on every pass; service
# restarts happen only when a persistent MTU setting actually changed.
#
# TWINPANEL_VPN_ACCESS_PERFORMANCE_RENDER_V89
# The controller emits an embedded Python program into a quoted shell heredoc.
# Newlines needed by that embedded program must be expressed without escape
# sequences that the outer f-string can consume while rendering. Using chr(10)
# keeps the generated remote Python syntactically stable and makes the payload
# directly compilable in CI before a release can reach production.
# ============================================================

RECONCILE_INTERVAL_SECONDS = 20.0
ACCESS_MTU = 1200
ACCESS_TCP_MSS = 1160

_PROTOCOL_SUBNETS = (
    "10.91.0.0/24",  # Cisco/OpenConnect
    "10.92.0.0/24",  # OpenVPN
    "10.93.0.0/24",  # WireGuard
    "10.94.0.0/24",  # L2TP
)

_last_detail_hash: dict[int, str] = {}


def _performance_script() -> str:
    subnet_lines = "\n".join(
        f"add_subnet '{subnet}'"
        for subnet in _PROTOCOL_SUBNETS
    )

    return f"""
set -e

ACCESS_MTU={ACCESS_MTU}
ACCESS_MSS={ACCESS_TCP_MSS}
WAN="$(ip -o -4 route show default | awk '{{for(i=1;i<=NF;i++) if($i==\"dev\"){{print $(i+1); exit}}}}')"
[ -n "$WAN" ]
ip link show dev "$WAN" >/dev/null 2>&1

sysctl -w net.ipv4.ip_forward=1 >/dev/null
sysctl -w net.ipv4.tcp_mtu_probing=1 >/dev/null

ipt() {{ iptables -w 5 "$@"; }}
ipt -t mangle -N TP_ACCESS_PERF 2>/dev/null || true
ipt -t mangle -C FORWARD -j TP_ACCESS_PERF 2>/dev/null || \
  ipt -t mangle -I FORWARD 1 -j TP_ACCESS_PERF
ipt -t mangle -F TP_ACCESS_PERF

add_subnet() {{
  SUBNET="$1"
  ipt -t mangle -A TP_ACCESS_PERF \
    -s "$SUBNET" -o "$WAN" -p tcp \
    --tcp-flags SYN,RST SYN \
    -j TCPMSS --set-mss "$ACCESS_MSS"
  ipt -t mangle -A TP_ACCESS_PERF \
    -d "$SUBNET" -i "$WAN" -p tcp \
    --tcp-flags SYN,RST SYN \
    -j TCPMSS --set-mss "$ACCESS_MSS"
}}

{subnet_lines}

python3 - <<'PY_REMOTE'
from pathlib import Path
import re

ACCESS_MTU = {ACCESS_MTU}
ACCESS_MSS = {ACCESS_TCP_MSS}


def replace_or_append(path: str, pattern: str, line: str) -> bool:
    p = Path(path)
    if not p.is_file():
        return False
    text = p.read_text(encoding="utf-8", errors="ignore")
    if re.search(pattern, text, flags=re.MULTILINE):
        updated = re.sub(pattern, line, text, count=1, flags=re.MULTILINE)
    else:
        updated = text.rstrip() + chr(10) + line + chr(10)
    if updated == text:
        return False
    backup = p.with_name(p.name + ".twinpanel-v51.bak")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
    p.write_text(updated, encoding="utf-8")
    return True


# Cisco/OpenConnect. A real restart is intentional only on config change: HUP
# can leave existing workers on the old negotiated MTU and hide the defect.
if replace_or_append(
    "/etc/ocserv/ocserv.conf",
    r"^[ \t]*mtu[ \t]*=.*$",
    f"mtu = {ACCESS_MTU}",
):
    Path("/run/twinpanel-v51-restart-ocserv").touch()
    print("CISCO_CONFIG_MTU=CHANGED")

# OpenVPN server. Client profiles already carry tun-mtu/mssfix; make the server
# authoritative too so fresh and existing deployments converge identically.
ovpn = "/etc/openvpn/server/twinpanel.conf"
ovpn_changed = False
ovpn_changed |= replace_or_append(
    ovpn,
    r"^[ \t]*tun-mtu[ \t]+.*$",
    f"tun-mtu {ACCESS_MTU}",
)
ovpn_changed |= replace_or_append(
    ovpn,
    r"^[ \t]*mssfix[ \t]+.*$",
    f"mssfix {{ACCESS_MSS}}",
)
if ovpn_changed:
    Path("/run/twinpanel-v51-restart-openvpn").touch()
    print("OPENVPN_CONFIG_MTU=CHANGED")

# WireGuard server config. Runtime interface MTU is repaired below as well.
p = Path("/etc/wireguard/wg-access0.conf")
if p.is_file():
    text = p.read_text(encoding="utf-8", errors="ignore")
    if re.search(r"(?m)^[ \t]*MTU[ \t]*=.*$", text):
        updated = re.sub(
            r"(?m)^[ \t]*MTU[ \t]*=.*$",
            f"MTU = {ACCESS_MTU}",
            text,
            count=1,
        )
    else:
        match = re.search(
            r"(?m)^" + re.escape("[Interface]") + r"[ \t]*$",
            text,
        )
        if match:
            pos = match.end()
            updated = text[:pos] + chr(10) + f"MTU = {ACCESS_MTU}" + text[pos:]
        else:
            updated = text
    if updated != text:
        backup = p.with_name(p.name + ".twinpanel-v51.bak")
        if not backup.exists():
            backup.write_text(text, encoding="utf-8")
        p.write_text(updated, encoding="utf-8")
        print("WIREGUARD_CONFIG_MTU=CHANGED")

# L2TP/PPP. Keep both directions bounded; restart xl2tpd only when these
# persistent values had to be repaired.
l2tp = "/etc/ppp/options.xl2tpd"
l2tp_changed = False
l2tp_changed |= replace_or_append(
    l2tp,
    r"^[ \t]*mtu[ \t]+.*$",
    f"mtu {ACCESS_MTU}",
)
l2tp_changed |= replace_or_append(
    l2tp,
    r"^[ \t]*mru[ \t]+.*$",
    f"mru {ACCESS_MTU}",
)
if l2tp_changed:
    Path("/run/twinpanel-v51-restart-xl2tpd").touch()
    print("L2TP_CONFIG_MTU=CHANGED")
PY_REMOTE

set_iface_mtu() {{
  IFACE="$1"
  [ -n "$IFACE" ] || return 0
  ip link show dev "$IFACE" >/dev/null 2>&1 || return 0
  CURRENT="$(cat "/sys/class/net/$IFACE/mtu" 2>/dev/null || true)"
  if [ "$CURRENT" != "$ACCESS_MTU" ]; then
    ip link set dev "$IFACE" mtu "$ACCESS_MTU"
    echo "MTU_CHANGED=$IFACE:$CURRENT->$ACCESS_MTU"
  fi
}}

for IFACE in $(ls /sys/class/net 2>/dev/null | grep '^vpns' || true); do
  set_iface_mtu "$IFACE"
done

OVPN_IF="$(ip -o -4 addr show | awk 'index($4,\"10.92.0.1/\")==1 {{print $2; exit}}')"
set_iface_mtu "$OVPN_IF"

WG_IF="$(ip -o -4 addr show | awk 'index($4,\"10.93.0.1/\")==1 {{print $2; exit}}')"
[ -n "$WG_IF" ] || WG_IF=wg-access0
set_iface_mtu "$WG_IF"

if [ -e /run/twinpanel-v51-restart-ocserv ]; then
  if systemctl is-active --quiet ocserv.service; then
    systemctl restart ocserv.service
    systemctl is-active --quiet ocserv.service
  fi
  rm -f /run/twinpanel-v51-restart-ocserv
fi

if [ -e /run/twinpanel-v51-restart-openvpn ]; then
  if systemctl is-active --quiet openvpn-server@twinpanel.service; then
    systemctl restart openvpn-server@twinpanel.service
    systemctl is-active --quiet openvpn-server@twinpanel.service
  fi
  rm -f /run/twinpanel-v51-restart-openvpn
fi

if [ -e /run/twinpanel-v51-restart-xl2tpd ]; then
  if systemctl is-active --quiet xl2tpd.service; then
    systemctl restart xl2tpd.service
    systemctl is-active --quiet xl2tpd.service
  fi
  rm -f /run/twinpanel-v51-restart-xl2tpd
fi

# Runtime verification. Missing services are acceptable on partial Exit nodes;
# an installed service with a wrong value is not.
if [ -f /etc/ocserv/ocserv.conf ]; then
  grep -Eq '^[[:space:]]*mtu[[:space:]]*=[[:space:]]*1200[[:space:]]*$' /etc/ocserv/ocserv.conf
fi
if [ -f /etc/openvpn/server/twinpanel.conf ]; then
  grep -Eq '^[[:space:]]*tun-mtu[[:space:]]+1200[[:space:]]*$' /etc/openvpn/server/twinpanel.conf
  grep -Eq '^[[:space:]]*mssfix[[:space:]]+1160[[:space:]]*$' /etc/openvpn/server/twinpanel.conf
fi
if [ -f /etc/wireguard/wg-access0.conf ]; then
  grep -Eq '^[[:space:]]*MTU[[:space:]]*=[[:space:]]*1200[[:space:]]*$' /etc/wireguard/wg-access0.conf
fi
if [ -f /etc/ppp/options.xl2tpd ]; then
  grep -Eq '^[[:space:]]*mtu[[:space:]]+1200[[:space:]]*$' /etc/ppp/options.xl2tpd
  grep -Eq '^[[:space:]]*mru[[:space:]]+1200[[:space:]]*$' /etc/ppp/options.xl2tpd
fi

for IFACE in $(ls /sys/class/net 2>/dev/null | grep '^vpns' || true); do
  [ "$(cat /sys/class/net/$IFACE/mtu)" = "$ACCESS_MTU" ]
done

if ip link show wg-access0 >/dev/null 2>&1; then
  [ "$(cat /sys/class/net/wg-access0/mtu)" = "$ACCESS_MTU" ]
fi

echo "V51_OK=1"
echo "WAN=$WAN"
echo "ACCESS_MTU=$ACCESS_MTU"
echo "ACCESS_MSS=$ACCESS_MSS"
ipt -t mangle -S TP_ACCESS_PERF
""".strip()


async def _reconcile_node(node_id: int) -> None:
    db = SessionLocal()
    conn = None

    try:
        node = db.get(Node, int(node_id))
        if (
            node is None
            or node.node_type != NodeType.EXIT
            or getattr(node, "retired_at", None) is not None
        ):
            return

        conn = await ssh_connect_saved(node, db)
        result = await conn.run(
            _performance_script(),
            check=False,
            timeout=90,
        )

        text = (
            str(result.stdout or "")
            + "\n"
            + str(result.stderr or "")
        ).strip()

        if result.exit_status != 0 or "V51_OK=1" not in text:
            raise RuntimeError(
                "vpn_access_performance_v51_failed: "
                + text[-3000:]
            )

        digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
        previous = _last_detail_hash.get(int(node.id))
        if previous != digest or "=CHANGED" in text:
            print(
                "TWINPANEL_VPN_ACCESS_PERFORMANCE_V51 "
                f"node={node.id} mtu={ACCESS_MTU} mss={ACCESS_TCP_MSS} "
                f"detail={text[-1600:]}",
                flush=True,
            )
            _last_detail_hash[int(node.id)] = digest

    finally:
        if conn is not None:
            conn.close()
            await conn.wait_closed()
        db.close()


async def reconcile_once() -> None:
    db = SessionLocal()
    try:
        node_ids = [
            int(row[0])
            for row in (
                db.query(Node.id)
                .filter(
                    Node.node_type == NodeType.EXIT,
                    Node.retired_at.is_(None),
                )
                .order_by(Node.id.asc())
                .all()
            )
        ]
    finally:
        db.close()

    semaphore = asyncio.Semaphore(2)

    async def run_one(node_id: int) -> None:
        async with semaphore:
            try:
                await _reconcile_node(node_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(
                    "TWINPANEL_VPN_ACCESS_PERFORMANCE_V51_ERROR "
                    f"node={node_id} error={type(exc).__name__}:{str(exc)[:1200]}",
                    flush=True,
                )

    await asyncio.gather(*(run_one(node_id) for node_id in node_ids))


async def reconciler_loop() -> None:
    print(
        "TWINPANEL_VPN_ACCESS_PERFORMANCE_V51_START "
        f"access_mtu={ACCESS_MTU} tcp_mss={ACCESS_TCP_MSS} "
        "render_fix=v89 "
        "exit_invariant=1 protocols=cisco,openvpn,wireguard,l2tp",
        flush=True,
    )

    while True:
        try:
            await reconcile_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                "TWINPANEL_VPN_ACCESS_PERFORMANCE_V51_PASS_ERROR "
                f"error={type(exc).__name__}:{str(exc)[:1200]}",
                flush=True,
            )

        await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)
