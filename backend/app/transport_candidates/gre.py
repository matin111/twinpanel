from __future__ import annotations

import asyncio
import hashlib
import json
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
# TWINPANEL TP27 GRE FAST CANARY V1
#
# Production-safe canary port of the proven TP27 data-plane strategy:
#   1) Native kernel GRE first (lowest overhead / fastest path)
#   2) GRE over UDP FOU when raw GRE is unavailable on the path
#
# The candidate remains isolated from the active tunnel until the operator
# explicitly promotes it. Existing Backhaul/TP2027/VPN services are not
# restarted or replaced by this installer.
# ============================================================

DEFAULT_MTU = 1400
TXQUEUELEN = 1000
FOU_PORT_CANDIDATES = (443, 8443, 2053, 2083, 10443)


def _gre_key(tunnel_id: int, iran_public: str, exit_public: str) -> int:
    raw = hashlib.sha256(
        f"twinpanel-tp27-fast|{int(tunnel_id)}|{iran_public}|{exit_public}".encode()
    ).digest()
    value = int.from_bytes(raw[:4], "big")
    return value or 1


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
    comment = f"TwinPanel-TP27FAST-{role}-{interface}"

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
COMMENT={shlex.quote(comment)}

remove_rules() {{
  if command -v iptables >/dev/null 2>&1; then
    while iptables -C INPUT -p 47 -s "$REMOTE_PUBLIC/32" -m comment --comment "$COMMENT-RAW-IN" -j ACCEPT 2>/dev/null; do
      iptables -D INPUT -p 47 -s "$REMOTE_PUBLIC/32" -m comment --comment "$COMMENT-RAW-IN" -j ACCEPT || break
    done

    if [ "$FOU_PORT" -gt 0 ]; then
      while iptables -C INPUT -p udp -s "$REMOTE_PUBLIC/32" --dport "$FOU_PORT" -m comment --comment "$COMMENT-FOU-IN" -j ACCEPT 2>/dev/null; do
        iptables -D INPUT -p udp -s "$REMOTE_PUBLIC/32" --dport "$FOU_PORT" -m comment --comment "$COMMENT-FOU-IN" -j ACCEPT || break
      done
    fi
  fi
}}

cleanup() {{
  remove_rules || true
  ip link del "$IFACE" >/dev/null 2>&1 || true
}}

if [ "$ACTION" = "stop" ]; then
  cleanup
  exit 0
fi

cleanup

modprobe ip_gre >/dev/null 2>&1 || true

if command -v iptables >/dev/null 2>&1; then
  if [ "$MODE" = "gre-fou" ]; then
    iptables -C INPUT -p udp -s "$REMOTE_PUBLIC/32" --dport "$FOU_PORT" -m comment --comment "$COMMENT-FOU-IN" -j ACCEPT >/dev/null 2>&1 || \
      iptables -I INPUT 1 -p udp -s "$REMOTE_PUBLIC/32" --dport "$FOU_PORT" -m comment --comment "$COMMENT-FOU-IN" -j ACCEPT
  else
    iptables -C INPUT -p 47 -s "$REMOTE_PUBLIC/32" -m comment --comment "$COMMENT-RAW-IN" -j ACCEPT >/dev/null 2>&1 || \
      iptables -I INPUT 1 -p 47 -s "$REMOTE_PUBLIC/32" -m comment --comment "$COMMENT-RAW-IN" -j ACCEPT
  fi
fi

if [ "$MODE" = "gre-fou" ]; then
  modprobe fou >/dev/null 2>&1 || true

  if ! ip fou add port "$FOU_PORT" ipproto 47 2>/dev/null; then
    ip fou show 2>/dev/null | grep -Eq "port[[:space:]]+$FOU_PORT([[:space:]]|$)" || {{
      echo "TP27_FAST_ERROR fou-register-failed port=$FOU_PORT" >&2
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
ip addr add "$ADDR" dev "$IFACE"
ip link set dev "$IFACE" up
sysctl -q -w "net.ipv4.conf.${{IFACE}}.rp_filter=0" >/dev/null 2>&1 || true

echo "TP27_FAST_READY role={role} mode=$MODE iface=$IFACE addr=$ADDR peer=$PEER mtu=$MTU fou_port=$FOU_PORT" >&2

FAILS=0
while true; do
  sleep 5

  if ! ip link show "$IFACE" >/dev/null 2>&1; then
    echo "TP27_FAST_SELFHEAL iface=$IFACE reason=interface-missing" >&2
    exit 75
  fi

  if ping -I "$IFACE" -c 1 -W 1 "$PEER" >/dev/null 2>&1; then
    FAILS=0
  else
    FAILS=$((FAILS + 1))
    if [ "$FAILS" -eq 4 ]; then
      echo "TP27_FAST_DEGRADED iface=$IFACE peer=$PEER action=hold-interface" >&2
    fi
    if [ "$FAILS" -gt 4 ]; then
      FAILS=4
    fi
  fi
done
'''


async def _port_available(conn, port: int) -> bool:
    result = await conn.run(
        f'''
set +e
PORT={int(port)}

if ip fou show 2>/dev/null | grep -Eq "port[[:space:]]+$PORT([[:space:]]|$)"; then
  echo TP27_FOU_PORT=existing
  exit 0
fi

if ss -H -lun 2>/dev/null | awk '{{print $5}}' | grep -Eq "[:.]$PORT$"; then
  echo TP27_FOU_PORT=busy
  exit 17
fi

echo TP27_FOU_PORT=free
exit 0
''',
        check=False,
        timeout=20,
    )
    return result.exit_status == 0


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
        helper = f"/usr/local/sbin/tp27-fast-{int(gre_key)}-{role}"
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
cat > {shlex.quote(helper)} <<'TP27FAST'
{content}TP27FAST
chmod 0755 {shlex.quote(helper)}

cat > /etc/systemd/system/{shlex.quote(service)} <<'UNIT'
[Unit]
Description=TwinPanel TP27 GRE FAST {role}
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
            f"tp27_fast_{role}_{mode}_install",
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
            raise RuntimeError("tp27_fast_public_ip_missing")

        gre_key = _gre_key(int(tunnel_id), iran_public, exit_public)
        mtu = DEFAULT_MTU

        # 1) Native kernel GRE: minimum overhead and preferred fast path.
        try:
            await _install_mode(
                ci=ci,
                ce=ce,
                rt=rt,
                iran_public=iran_public,
                exit_public=exit_public,
                gre_key=gre_key,
                mode="gre",
                fou_port=None,
                mtu=mtu,
            )
            health = await probe(
                ci,
                ce,
                name=name,
                tunnel_id=tunnel_id,
                rt=rt,
            )

            meta = {
                **rt,
                **health,
                "tp27_fast": True,
                "mode": "gre-native",
                "gre_key": gre_key,
                "mtu": mtu,
                "txqueuelen": TXQUEUELEN,
            }
            mark(
                db,
                tunnel_id,
                name,
                status="online",
                latency_ms=health["latency_ms"],
                meta=json.dumps(meta),
            )
            return {
                "ok": True,
                "transport": name,
                "runtime": meta,
                "probe": health,
            }
        except Exception as exc:
            attempts.append(f"raw_gre:{type(exc).__name__}:{exc}")
            await _cleanup_pair(ci, ce, rt)

        # 2) TP27-style GRE/UDP FOU fallback. Probe a bounded port list and
        # keep the first path that passes full bidirectional + TCP/UDP egress.
        for fou_port in FOU_PORT_CANDIDATES:
            iran_free, exit_free = await asyncio.gather(
                _port_available(ci, fou_port),
                _port_available(ce, fou_port),
            )
            if not (iran_free and exit_free):
                attempts.append(f"fou_{fou_port}:port_busy")
                continue

            try:
                await _install_mode(
                    ci=ci,
                    ce=ce,
                    rt=rt,
                    iran_public=iran_public,
                    exit_public=exit_public,
                    gre_key=gre_key,
                    mode="gre-fou",
                    fou_port=fou_port,
                    mtu=mtu,
                )
                health = await probe(
                    ci,
                    ce,
                    name=name,
                    tunnel_id=tunnel_id,
                    rt=rt,
                )

                meta = {
                    **rt,
                    **health,
                    "tp27_fast": True,
                    "mode": "gre-fou",
                    "fou_port": fou_port,
                    "gre_key": gre_key,
                    "mtu": mtu,
                    "txqueuelen": TXQUEUELEN,
                }
                mark(
                    db,
                    tunnel_id,
                    name,
                    status="online",
                    latency_ms=health["latency_ms"],
                    meta=json.dumps(meta),
                )
                return {
                    "ok": True,
                    "transport": name,
                    "runtime": meta,
                    "probe": health,
                }
            except Exception as exc:
                attempts.append(
                    f"fou_{fou_port}:{type(exc).__name__}:{exc}"
                )
                await _cleanup_pair(ci, ce, rt)

        raise RuntimeError(
            "tp27_fast_all_paths_failed: " + " | ".join(attempts)[-5000:]
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
