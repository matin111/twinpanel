from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shlex

from sqlalchemy.orm import Session

from .common import (
    close_pair,
    connect_pair,
    diag,
    mark,
    prerequisites,
    probe,
    run,
    runtime,
    tunnel_nodes,
)


# ============================================================
# TWINPANEL TP27 CORE PARITY V2
#
# This adapter mirrors the important runtime/selection semantics of
# matin111/tp27-core's current GRE data plane:
#   * raw kernel GRE first
#   * GRE/UDP FOU fallback on a bounded port list
#   * dedicated /30 per tunnel
#   * MTU 1400 / txqueuelen 1000
#   * per-interface rp_filter only
#   * narrow INPUT/OUTPUT/FORWARD allow rules owned by this interface
#   * keepalive considers both peer ping and RX byte progress
#   * shared/global FOU registrations are never deleted on stop
#
# Critical parity change versus the old TwinPanel canary:
# mode selection is gated by bidirectional L3 peer health, like tp27-core.
# The broader internet egress probe is retained only as diagnostic telemetry;
# it no longer rejects a healthy raw-GRE link and forces a slower FOU fallback.
# ============================================================

DEFAULT_MTU = 1400
TXQUEUELEN = 1000
KEEPALIVE_INTERVAL = 5
KEEPALIVE_FAILURES = 4
FOU_PORT_CANDIDATES = (443, 8443, 2053, 2083, 10443)


def _gre_key(tunnel_id: int, iran_public: str, exit_public: str) -> int:
    raw = hashlib.sha256(
        f"twinpanel-tp27-core|{int(tunnel_id)}|{iran_public}|{exit_public}".encode()
    ).digest()
    value = int.from_bytes(raw[:4], "big")
    return value or 1


def _chain_suffix(interface: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9]", "", interface)[:12]
    return clean or "TP27"


def _helper_text(
    *,
    interface: str,
    local_public: str,
    remote_public: str,
    local_addr: str,
    peer_ip: str,
    gre_key: int,
    mode: str,
    fou_port: int | None,
    role: str,
    mtu: int,
) -> str:
    port = int(fou_port or 0)
    suffix = _chain_suffix(interface)
    chain_in = f"TPF_{suffix}_IN"[:28]
    chain_out = f"TPF_{suffix}_OUT"[:28]
    chain_fwd = f"TPF_{suffix}_FWD"[:28]

    return f'''#!/bin/bash
set -Eeuo pipefail

ACTION="${{1:-run}}"
IFACE={shlex.quote(interface)}
LOCAL_PUBLIC={shlex.quote(local_public)}
REMOTE_PUBLIC={shlex.quote(remote_public)}
ADDR={shlex.quote(local_addr)}
PEER={shlex.quote(peer_ip)}
GRE_KEY={int(gre_key)}
MODE={shlex.quote(mode)}
FOU_PORT={port}
MTU={int(mtu)}
TXQLEN={int(TXQUEUELEN)}
KEEPALIVE_INTERVAL={int(KEEPALIVE_INTERVAL)}
KEEPALIVE_FAILURES={int(KEEPALIVE_FAILURES)}
CHAIN_IN={shlex.quote(chain_in)}
CHAIN_OUT={shlex.quote(chain_out)}
CHAIN_FWD={shlex.quote(chain_fwd)}

ensure_chain_hook() {{
  local parent="$1" chain="$2"
  command -v iptables >/dev/null 2>&1 || return 0
  iptables -w 5 -N "$chain" 2>/dev/null || true
  iptables -w 5 -C "$parent" -j "$chain" 2>/dev/null || \
    iptables -w 5 -I "$parent" 1 -j "$chain"
}}

ensure_rule() {{
  local chain="$1"; shift
  command -v iptables >/dev/null 2>&1 || return 0
  iptables -w 5 -C "$chain" "$@" 2>/dev/null || \
    iptables -w 5 -A "$chain" "$@"
}}

remove_rule() {{
  local chain="$1"; shift
  command -v iptables >/dev/null 2>&1 || return 0
  while iptables -w 5 -C "$chain" "$@" 2>/dev/null; do
    iptables -w 5 -D "$chain" "$@" 2>/dev/null || break
  done
}}

setup_firewall() {{
  command -v iptables >/dev/null 2>&1 || return 0
  ensure_chain_hook INPUT "$CHAIN_IN"
  ensure_chain_hook OUTPUT "$CHAIN_OUT"
  ensure_chain_hook FORWARD "$CHAIN_FWD"

  ensure_rule "$CHAIN_IN" -i "$IFACE" -j ACCEPT
  ensure_rule "$CHAIN_OUT" -o "$IFACE" -j ACCEPT
  ensure_rule "$CHAIN_FWD" -i "$IFACE" -j ACCEPT
  ensure_rule "$CHAIN_FWD" -o "$IFACE" -j ACCEPT

  if [ "$MODE" = "gre-fou" ]; then
    ensure_rule "$CHAIN_IN" -p udp -s "$REMOTE_PUBLIC/32" -d "$LOCAL_PUBLIC/32" --dport "$FOU_PORT" -j ACCEPT
    ensure_rule "$CHAIN_OUT" -p udp -s "$LOCAL_PUBLIC/32" -d "$REMOTE_PUBLIC/32" --sport "$FOU_PORT" --dport "$FOU_PORT" -j ACCEPT
  else
    ensure_rule "$CHAIN_IN" -p 47 -s "$REMOTE_PUBLIC/32" -d "$LOCAL_PUBLIC/32" -j ACCEPT
    ensure_rule "$CHAIN_OUT" -p 47 -s "$LOCAL_PUBLIC/32" -d "$REMOTE_PUBLIC/32" -j ACCEPT
  fi
}}

cleanup_firewall() {{
  command -v iptables >/dev/null 2>&1 || return 0

  remove_rule "$CHAIN_IN" -i "$IFACE" -j ACCEPT
  remove_rule "$CHAIN_OUT" -o "$IFACE" -j ACCEPT
  remove_rule "$CHAIN_FWD" -i "$IFACE" -j ACCEPT
  remove_rule "$CHAIN_FWD" -o "$IFACE" -j ACCEPT

  if [ "$MODE" = "gre-fou" ]; then
    remove_rule "$CHAIN_IN" -p udp -s "$REMOTE_PUBLIC/32" -d "$LOCAL_PUBLIC/32" --dport "$FOU_PORT" -j ACCEPT
    remove_rule "$CHAIN_OUT" -p udp -s "$LOCAL_PUBLIC/32" -d "$REMOTE_PUBLIC/32" --sport "$FOU_PORT" --dport "$FOU_PORT" -j ACCEPT
  else
    remove_rule "$CHAIN_IN" -p 47 -s "$REMOTE_PUBLIC/32" -d "$LOCAL_PUBLIC/32" -j ACCEPT
    remove_rule "$CHAIN_OUT" -p 47 -s "$LOCAL_PUBLIC/32" -d "$REMOTE_PUBLIC/32" -j ACCEPT
  fi
}}

cleanup() {{
  cleanup_firewall || true
  ip link del "$IFACE" >/dev/null 2>&1 || true
  # FOU registrations are global kernel state and may be shared by another
  # TP27 link, so intentionally keep them registered.
  true
}}

if [ "$ACTION" = "stop" ]; then
  cleanup
  exit 0
fi

cleanup

modprobe ip_gre >/dev/null 2>&1 || true

if [ "$MODE" = "gre-fou" ]; then
  modprobe fou >/dev/null 2>&1 || true

  if ! ip fou add port "$FOU_PORT" ipproto 47 2>/dev/null; then
    ip fou show 2>/dev/null | grep -Eq "port[[:space:]]+$FOU_PORT([[:space:]]|$)" || {{
      echo "TP27_CORE_ERROR fou-register-failed port=$FOU_PORT" >&2
      exit 41
    }}
  fi

  ip link add "$IFACE" type gre \
    local "$LOCAL_PUBLIC" remote "$REMOTE_PUBLIC" \
    key "$GRE_KEY" ttl 255 \
    encap fou encap-sport "$FOU_PORT" encap-dport "$FOU_PORT"
else
  ip tunnel add "$IFACE" mode gre \
    local "$LOCAL_PUBLIC" remote "$REMOTE_PUBLIC" \
    ttl 255 key "$GRE_KEY"
fi

ip link set dev "$IFACE" mtu "$MTU" txqueuelen "$TXQLEN"
ip addr flush dev "$IFACE" scope global >/dev/null 2>&1 || true
ip addr add "$ADDR" dev "$IFACE"
ip link set dev "$IFACE" up
sysctl -q -w "net.ipv4.conf.${{IFACE}}.rp_filter=0" >/dev/null 2>&1 || true
setup_firewall

echo "TP27_CORE_READY role={role} mode=$MODE iface=$IFACE addr=$ADDR peer=$PEER mtu=$MTU fou_port=$FOU_PORT" >&2
ip -br -4 addr show dev "$IFACE" >&2 || true
ip -4 route show dev "$IFACE" >&2 || true

FAILS=0
LAST_RX="$(cat "/sys/class/net/${{IFACE}}/statistics/rx_bytes" 2>/dev/null || echo 0)"

while true; do
  sleep "$KEEPALIVE_INTERVAL"

  if ! ip link show "$IFACE" >/dev/null 2>&1; then
    echo "TP27_CORE_SELFHEAL iface=$IFACE reason=interface-missing" >&2
    exit 75
  fi

  RX_NOW="$(cat "/sys/class/net/${{IFACE}}/statistics/rx_bytes" 2>/dev/null || echo 0)"
  PING_OK=0

  if ping -I "$IFACE" -c 2 -i 0.2 -W 1 "$PEER" >/dev/null 2>&1; then
    PING_OK=1
  fi

  if [ "$PING_OK" -eq 1 ] || [ "$RX_NOW" -gt "$LAST_RX" ]; then
    if [ "$FAILS" -gt 0 ]; then
      echo "TP27_CORE_RECOVERED iface=$IFACE failures=$FAILS rx=$RX_NOW" >&2
    fi
    FAILS=0
  else
    FAILS=$((FAILS + 1))
    if [ "$FAILS" -lt "$KEEPALIVE_FAILURES" ]; then
      echo "TP27_CORE_KEEPALIVE_FAIL iface=$IFACE peer=$PEER failure=$FAILS/$KEEPALIVE_FAILURES rx=$RX_NOW" >&2
    elif [ "$FAILS" -eq "$KEEPALIVE_FAILURES" ]; then
      echo "TP27_CORE_DEGRADED iface=$IFACE peer=$PEER failures=$FAILS action=hold-interface" >&2
    else
      FAILS="$KEEPALIVE_FAILURES"
    fi
  fi

  LAST_RX="$RX_NOW"
done
'''


async def _port_available(conn, port: int) -> bool:
    result = await conn.run(
        f'''
set +e
PORT={int(port)}

if ip fou show 2>/dev/null | grep -Eq "port[[:space:]]+$PORT([[:space:]]|$)"; then
  echo TP27_FOU_PORT=existing
elif ss -H -lun 2>/dev/null | awk '{{print $5}}' | grep -Eq "[:.]$PORT$"; then
  echo TP27_FOU_PORT=busy
else
  echo TP27_FOU_PORT=free
fi

true
''',
        check=False,
        timeout=20,
    )
    text = (result.stdout or "").strip()
    return "TP27_FOU_PORT=busy" not in text


async def _cleanup_pair(ci, ce, rt: dict) -> None:
    async def one(conn, service: str, interface: str) -> None:
        await conn.run(
            f'''
set +e
systemctl stop {shlex.quote(service)} >/dev/null 2>&1 || true
ip link del {shlex.quote(interface)} >/dev/null 2>&1 || true
true
''',
            check=False,
            timeout=25,
        )

    await asyncio.gather(
        one(ci, rt["iran_service"], rt["interface"]),
        one(ce, rt["exit_service"], rt["interface"]),
    )


async def _install_mode(
    *,
    ci,
    ce,
    rt: dict,
    iran_public: str,
    exit_public: str,
    gre_key: int,
    mode: str,
    fou_port: int | None,
    mtu: int,
) -> None:
    async def peer(
        conn,
        *,
        role: str,
        local_public: str,
        remote_public: str,
        local_addr: str,
        peer_ip: str,
        service: str,
    ) -> None:
        helper = f"/usr/local/sbin/tp27-core-{int(gre_key)}-{role}"
        content = _helper_text(
            interface=rt["interface"],
            local_public=local_public,
            remote_public=remote_public,
            local_addr=local_addr,
            peer_ip=peer_ip,
            gre_key=gre_key,
            mode=mode,
            fou_port=fou_port,
            role=role,
            mtu=mtu,
        )

        await run(
            conn,
            f'''
set -e
cat > {shlex.quote(helper)} <<'TP27CORE'
{content}TP27CORE
chmod 0755 {shlex.quote(helper)}

cat > /etc/systemd/system/{shlex.quote(service)} <<'UNIT'
[Unit]
Description=TwinPanel TP27 Core Parity {role}
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart={helper} run
ExecStop={helper} stop
Restart=on-failure
RestartSec=2
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable {shlex.quote(service)} >/dev/null
systemctl restart {shlex.quote(service)}
''',
            f"tp27_core_{role}_{mode}_install",
            90,
        )

    await asyncio.gather(
        peer(
            ci,
            role="iran",
            local_public=iran_public,
            remote_public=exit_public,
            local_addr=rt["iran_addr"],
            peer_ip=rt["exit_ip"],
            service=rt["iran_service"],
        ),
        peer(
            ce,
            role="exit",
            local_public=exit_public,
            remote_public=iran_public,
            local_addr=rt["exit_addr"],
            peer_ip=rt["iran_ip"],
            service=rt["exit_service"],
        ),
    )

    await asyncio.sleep(2)


async def _peer_health(ci, ce, rt: dict) -> dict:
    p1, p2 = await asyncio.gather(
        ci.run(
            f"ping -I {shlex.quote(rt['interface'])} -c 4 -i 0.2 -W 2 {shlex.quote(rt['exit_ip'])}",
            check=False,
            timeout=15,
        ),
        ce.run(
            f"ping -I {shlex.quote(rt['interface'])} -c 4 -i 0.2 -W 2 {shlex.quote(rt['iran_ip'])}",
            check=False,
            timeout=15,
        ),
    )

    if p1.exit_status != 0 or p2.exit_status != 0:
        raise RuntimeError(
            f"peer_ping_failed: iran={p1.exit_status} exit={p2.exit_status}"
        )

    latency = None
    match = re.search(r"=\s*[0-9.]+/([0-9.]+)/", (p1.stdout or ""))
    if match:
        latency = max(1, int(round(float(match.group(1)))))

    return {
        "peer_ping": True,
        "bidirectional_l3": True,
        "latency_ms": latency,
        "selection_health": "tp27_core_peer_l3",
    }


async def _full_probe_diagnostic(ci, ce, *, tunnel_id: int, rt: dict) -> dict:
    try:
        result = await probe(
            ci,
            ce,
            name="kernel_gre",
            tunnel_id=tunnel_id,
            rt=rt,
        )
        return {
            "full_probe_ok": True,
            "full_probe": result,
        }
    except Exception as exc:
        return {
            "full_probe_ok": False,
            "full_probe_error": f"{type(exc).__name__}:{exc}"[:1800],
        }


async def install(tunnel_id: int, db: Session) -> dict:
    name = "kernel_gre"
    _, iran, exit_node = tunnel_nodes(db, tunnel_id)
    rt = runtime(name, tunnel_id)
    mark(db, tunnel_id, name, status="installing", meta=json.dumps(rt))

    ci = ce = None
    attempts: list[str] = []

    try:
        ci, ce = await connect_pair(iran, exit_node, db)
        await asyncio.gather(prerequisites(ci), prerequisites(ce))

        iran_public = str(iran.public_ip or "").strip()
        exit_public = str(exit_node.public_ip or "").strip()
        if not iran_public or not exit_public:
            raise RuntimeError("tp27_core_public_ip_missing")

        gre_key = _gre_key(int(tunnel_id), iran_public, exit_public)
        mtu = DEFAULT_MTU

        async def accept_mode(mode: str, fou_port: int | None) -> dict:
            await _install_mode(
                ci=ci,
                ce=ce,
                rt=rt,
                iran_public=iran_public,
                exit_public=exit_public,
                gre_key=gre_key,
                mode=mode,
                fou_port=fou_port,
                mtu=mtu,
            )

            peer = await _peer_health(ci, ce, rt)
            diagnostic = await _full_probe_diagnostic(
                ci,
                ce,
                tunnel_id=tunnel_id,
                rt=rt,
            )

            meta = {
                **rt,
                **peer,
                **diagnostic,
                "tp27_fast": True,
                "tp27_core_parity": True,
                "tp27_core_source": "bin/tp27-link-mtls",
                "mode": "gre-fou" if mode == "gre-fou" else "gre-native",
                "fou_port": fou_port,
                "gre_key": gre_key,
                "mtu": mtu,
                "txqueuelen": TXQUEUELEN,
                "keepalive_interval": KEEPALIVE_INTERVAL,
                "keepalive_failures": KEEPALIVE_FAILURES,
                "selection_gate": "bidirectional_peer_l3",
                "full_probe_is_diagnostic_only": True,
                "attempts": list(attempts),
            }

            mark(
                db,
                tunnel_id,
                name,
                status="online",
                latency_ms=peer.get("latency_ms"),
                meta=json.dumps(meta),
            )

            return {
                "ok": True,
                "transport": name,
                "runtime": meta,
                "probe": peer,
            }

        # Match tp27-core: healthy raw kernel GRE wins on peer-L3 health.
        try:
            return await accept_mode("gre", None)
        except Exception as exc:
            attempts.append(f"raw_gre:{type(exc).__name__}:{exc}")
            await _cleanup_pair(ci, ce, rt)

        # Only if raw GRE itself cannot establish bidirectional L3 do we fall
        # back to GRE/UDP FOU, in the same bounded order as tp27-core.
        for fou_port in FOU_PORT_CANDIDATES:
            iran_free, exit_free = await asyncio.gather(
                _port_available(ci, fou_port),
                _port_available(ce, fou_port),
            )

            if not (iran_free and exit_free):
                attempts.append(f"fou_{fou_port}:port_busy")
                continue

            try:
                return await accept_mode("gre-fou", fou_port)
            except Exception as exc:
                attempts.append(
                    f"fou_{fou_port}:{type(exc).__name__}:{exc}"
                )
                await _cleanup_pair(ci, ce, rt)

        raise RuntimeError(
            "tp27_core_all_paths_failed: " + " | ".join(attempts)[-5000:]
        )

    except Exception as exc:
        a = await diag(ci, rt["iran_service"], rt["interface"]) if ci else ""
        b = await diag(ce, rt["exit_service"], rt["interface"]) if ce else ""
        msg = (
            f"{type(exc).__name__}: {exc} | "
            f"iran={a[-1800:]} | exit={b[-1800:]}"
        )
        mark(db, tunnel_id, name, status="failed", error=msg)
        raise RuntimeError(msg) from exc

    finally:
        await close_pair(ci, ce)
