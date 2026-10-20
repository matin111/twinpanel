from __future__ import annotations

import asyncio
import hashlib
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
# TWINPANEL TP27 FAST CARRIER V91
#
# Ported from matin111/tp27-core:
#   1) Raw keyed GRE in the Linux kernel (fast path)
#   2) GRE-in-UDP/FoU fallback when protocol 47 is unusable
#
# This is one logical SmartAuto candidate. The internal carrier profile is
# selected fail-closed and persisted in TunnelTransport.config_text; SmartAuto
# never sees raw GRE and FoU as competing logical tunnels.
# ============================================================

NAME = "tp27_fast"
MTU = 1400
TXQUEUELEN = 1000
FOU_PORT_CANDIDATES = (443, 8443, 2053, 2083, 10443)


def _gre_key(tunnel_id: int, iran_public: str, exit_public: str) -> int:
    raw = hashlib.sha256(
        f"{int(tunnel_id)}|{iran_public}|{exit_public}".encode()
    ).digest()
    value = int.from_bytes(raw[:4], "big")
    return value or 1


async def _reset_pair(ci, ce, rt: dict) -> None:
    await asyncio.gather(
        ci.run(
            f"""
set +e
systemctl disable --now {shlex.quote(rt['iran_service'])} >/dev/null 2>&1 || true
ip link del {shlex.quote(rt['interface'])} >/dev/null 2>&1 || true
true
""",
            check=False,
        ),
        ce.run(
            f"""
set +e
systemctl disable --now {shlex.quote(rt['exit_service'])} >/dev/null 2>&1 || true
ip link del {shlex.quote(rt['interface'])} >/dev/null 2>&1 || true
true
""",
            check=False,
        ),
    )


async def _install_peer(
    conn,
    *,
    tunnel_id: int,
    role: str,
    service: str,
    interface: str,
    local_public: str,
    remote_public: str,
    local_addr: str,
    gre_key: int,
    profile: str,
    fou_port: int | None,
) -> None:
    helper = f"/usr/local/sbin/tp27-fast-{int(tunnel_id)}-{role}"
    comment = f"TwinPanel-TP27-{int(tunnel_id)}-{role}"

    if profile == "gre-native":
        firewall = f"""
while iptables -C INPUT -p udp -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT 2>/dev/null; do
  iptables -D INPUT -p udp -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT || break
done
iptables -C INPUT -p 47 -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT 2>/dev/null || \
iptables -I INPUT -p 47 -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT
"""
        link = "ip tunnel add \"$IFACE\" mode gre local \"$LOCAL\" remote \"$REMOTE\" ttl 255 key \"$KEY\""
    else:
        port = int(fou_port or 0)
        if port <= 0:
            raise RuntimeError("tp27_fou_port_missing")
        firewall = f"""
while iptables -C INPUT -p 47 -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT 2>/dev/null; do
  iptables -D INPUT -p 47 -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT || break
done
iptables -C INPUT -p udp --dport {port} -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT 2>/dev/null || \
iptables -I INPUT -p udp --dport {port} -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT
"""
        link = (
            f"ip fou add port {port} ipproto 47 >/dev/null 2>&1 || true\n"
            "ip link add \"$IFACE\" type gre local \"$LOCAL\" remote \"$REMOTE\" "
            f"ttl 255 key \"$KEY\" encap fou encap-sport auto encap-dport {port}"
        )

    await run(
        conn,
        f"""
set -e
modprobe ip_gre >/dev/null 2>&1 || true
modprobe fou >/dev/null 2>&1 || true

cat > {shlex.quote(helper)} <<'EOF'
#!/bin/bash
set -e
ACTION="${{1:-start}}"
IFACE={interface}
LOCAL={local_public}
REMOTE={remote_public}
ADDR={local_addr}
KEY={int(gre_key)}
COMMENT={comment}

cleanup_rules() {{
  if ! command -v iptables >/dev/null 2>&1; then
    return 0
  fi
  while iptables -C INPUT -p 47 -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT 2>/dev/null; do
    iptables -D INPUT -p 47 -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT || break
  done
  for p in 443 8443 2053 2083 10443; do
    while iptables -C INPUT -p udp --dport "$p" -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT 2>/dev/null; do
      iptables -D INPUT -p udp --dport "$p" -s "$REMOTE" -m comment --comment "$COMMENT" -j ACCEPT || break
    done
  done
}}

if [ "$ACTION" = stop ]; then
  ip link del "$IFACE" >/dev/null 2>&1 || true
  cleanup_rules
  exit 0
fi

ip link del "$IFACE" >/dev/null 2>&1 || true
cleanup_rules

if command -v iptables >/dev/null 2>&1; then
{firewall}
fi

{link}
ip addr add "$ADDR" dev "$IFACE"
ip link set dev "$IFACE" mtu {MTU} txqueuelen {TXQUEUELEN} up
EOF

chmod 755 {shlex.quote(helper)}
cat > /etc/systemd/system/{shlex.quote(service)} <<'EOF'
[Unit]
Description=TwinPanel TP27 Fast {int(tunnel_id)} {role} ({profile})
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart={helper} start
ExecStop={helper} stop

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable {shlex.quote(service)} >/dev/null
systemctl restart {shlex.quote(service)}
""",
        f"tp27_{profile}_{role}_install",
        90,
    )


async def _install_profile(
    ci,
    ce,
    *,
    tunnel_id: int,
    iran_public: str,
    exit_public: str,
    rt: dict,
    gre_key: int,
    profile: str,
    fou_port: int | None = None,
) -> None:
    await _reset_pair(ci, ce, rt)

    await asyncio.gather(
        _install_peer(
            ci,
            tunnel_id=tunnel_id,
            role="iran",
            service=rt["iran_service"],
            interface=rt["interface"],
            local_public=iran_public,
            remote_public=exit_public,
            local_addr=rt["iran_addr"],
            gre_key=gre_key,
            profile=profile,
            fou_port=fou_port,
        ),
        _install_peer(
            ce,
            tunnel_id=tunnel_id,
            role="exit",
            service=rt["exit_service"],
            interface=rt["interface"],
            local_public=exit_public,
            remote_public=iran_public,
            local_addr=rt["exit_addr"],
            gre_key=gre_key,
            profile=profile,
            fou_port=fou_port,
        ),
    )

    # Give the kernel link and routes a bounded settling interval. The full
    # common probe below remains authoritative for qualification.
    await asyncio.sleep(1.5)


async def install(tunnel_id: int, db: Session) -> dict:
    _, iran, exit_node = tunnel_nodes(db, tunnel_id)
    rt = runtime(NAME, tunnel_id)
    gre_key = _gre_key(
        tunnel_id,
        str(iran.public_ip),
        str(exit_node.public_ip),
    )

    mark(
        db,
        tunnel_id,
        NAME,
        status="installing",
        meta=str(
            {
                **rt,
                "source": "matin111/tp27-core",
                "profile_order": ["gre-native", "gre-fou"],
                "mtu": MTU,
                "gre_key": gre_key,
            }
        ),
    )

    ci = ce = None
    attempts: list[dict] = []

    try:
        ci, ce = await connect_pair(iran, exit_node, db)
        await asyncio.gather(prerequisites(ci), prerequisites(ce))

        # Fastest path first: native keyed GRE in-kernel.
        try:
            await _install_profile(
                ci,
                ce,
                tunnel_id=tunnel_id,
                iran_public=str(iran.public_ip),
                exit_public=str(exit_node.public_ip),
                rt=rt,
                gre_key=gre_key,
                profile="gre-native",
            )
            health = await probe(
                ci,
                ce,
                name=NAME,
                tunnel_id=tunnel_id,
                rt=rt,
            )
            attempts.append({"profile": "gre-native", "result": "online"})

            meta = {
                **rt,
                **health,
                "source": "matin111/tp27-core",
                "selected_profile": "gre-native",
                "gre_key": gre_key,
                "mtu": MTU,
                "attempts": attempts,
            }
            mark(
                db,
                tunnel_id,
                NAME,
                status="online",
                latency_ms=health["latency_ms"],
                meta=str(meta),
            )
            return {
                "ok": True,
                "transport": NAME,
                "runtime": rt,
                "profile": "gre-native",
                "probe": health,
            }
        except Exception as exc:
            attempts.append(
                {
                    "profile": "gre-native",
                    "result": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

        # TP27 fallback: GRE encapsulated in UDP/FoU. Try the same bounded port
        # set as the reference implementation and accept only a full L3 probe.
        for fou_port in FOU_PORT_CANDIDATES:
            try:
                await _install_profile(
                    ci,
                    ce,
                    tunnel_id=tunnel_id,
                    iran_public=str(iran.public_ip),
                    exit_public=str(exit_node.public_ip),
                    rt=rt,
                    gre_key=gre_key,
                    profile="gre-fou",
                    fou_port=fou_port,
                )
                health = await probe(
                    ci,
                    ce,
                    name=NAME,
                    tunnel_id=tunnel_id,
                    rt=rt,
                )
                attempts.append(
                    {
                        "profile": "gre-fou",
                        "port": fou_port,
                        "result": "online",
                    }
                )
                meta = {
                    **rt,
                    **health,
                    "source": "matin111/tp27-core",
                    "selected_profile": "gre-fou",
                    "fou_port": fou_port,
                    "gre_key": gre_key,
                    "mtu": MTU,
                    "attempts": attempts,
                }
                mark(
                    db,
                    tunnel_id,
                    NAME,
                    status="online",
                    latency_ms=health["latency_ms"],
                    meta=str(meta),
                )
                return {
                    "ok": True,
                    "transport": NAME,
                    "runtime": rt,
                    "profile": "gre-fou",
                    "fou_port": fou_port,
                    "probe": health,
                }
            except Exception as exc:
                attempts.append(
                    {
                        "profile": "gre-fou",
                        "port": fou_port,
                        "result": "failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        await _reset_pair(ci, ce, rt)
        raise RuntimeError(f"tp27_all_profiles_failed: {attempts!r}")

    except Exception as exc:
        a = await diag(ci, rt["iran_service"], rt["interface"]) if ci else ""
        b = await diag(ce, rt["exit_service"], rt["interface"]) if ce else ""
        msg = (
            f"{type(exc).__name__}: {exc} | "
            f"iran={a[-1800:]} | exit={b[-1800:]}"
        )
        mark(db, tunnel_id, NAME, status="failed", error=msg)
        raise RuntimeError(msg) from exc
    finally:
        await close_pair(ci, ce)
