from __future__ import annotations

import asyncio
import json
import shlex
from datetime import datetime

from sqlalchemy.orm import Session

from .models import Node, Tunnel
from .routers.provision import ssh_connect_saved
from .ssh_relay import (
    _member,
    _write,
    relay_addresses,
    relay_interface,
    verify_ssh_relay,
)
from .ssh_relay_v2 import _run
from .ssh_relay_v21 import (
    apply_carrier_aware_relay_v21,
    provision_ssh_relay_v21,
)


# ============================================================
# TWINPANEL SSH RELAY V22
#
# V21 solved the blocked Iran -> Relay public first hop by
# borrowing an already healthy Backhaul tunnel as a read-only
# carrier.
#
# V22 completes the actual Internet data plane:
#
#   Iran source 10.80.x.1
#        |
#        | policy table 27000+tunnel_id
#        v
#      tun1xx
#        |
#        v
#   Final Exit
#        |
#        | targeted FORWARD + MASQUERADE
#        v
#     Internet
#
# Carrier tunnel/service/interface/routing is NEVER changed.
# ============================================================


def _route_table(tunnel_id: int) -> int:
    return 27000 + int(tunnel_id)


def _route_service(tunnel_id: int) -> str:
    return (
        f"tp{int(tunnel_id)}-"
        "relay-route.service"
    )


def _egress_service(tunnel_id: int) -> str:
    return (
        f"tp{int(tunnel_id)}-"
        "relay-egress.service"
    )


def _route_helper(tunnel_id: int) -> str:
    return (
        "/usr/local/sbin/"
        f"tp{int(tunnel_id)}-relay-route"
    )


def _egress_helper(tunnel_id: int) -> str:
    return (
        "/usr/local/sbin/"
        f"tp{int(tunnel_id)}-relay-egress"
    )


async def _disable_v22_helpers(
    ci,
    ce,
    tunnel_id: int,
) -> None:
    tid = int(tunnel_id)

    if ci is not None:
        await _run(
            ci,
            (
                "systemctl disable --now "
                f"{shlex.quote(_route_service(tid))} "
                ">/dev/null 2>&1 || true; "
                f"{shlex.quote(_route_helper(tid))} cleanup "
                ">/dev/null 2>&1 || true"
            ),
            check=False,
            timeout=20,
        )

    if ce is not None:
        await _run(
            ce,
            (
                "systemctl disable --now "
                f"{shlex.quote(_egress_service(tid))} "
                ">/dev/null 2>&1 || true; "
                f"{shlex.quote(_egress_helper(tid))} cleanup "
                ">/dev/null 2>&1 || true"
            ),
            check=False,
            timeout=20,
        )


async def _install_full_egress_v22(
    tunnel: Tunnel,
    iran: Node,
    exit_node: Node,
    db: Session,
) -> dict:
    tid = int(tunnel.id)

    iface = relay_interface(
        tunnel
    )

    (
        network,
        iran_ip,
        exit_ip,
    ) = relay_addresses(
        tunnel
    )

    table = _route_table(
        tid
    )

    pref = table

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
        # Iran: source-specific default route.
        #
        # This does NOT touch the main table and does NOT touch
        # the carrier Backhaul routing table.
        # ----------------------------------------------------

        route_script = f"""#!/bin/bash
set -u

IFACE={shlex.quote(iface)}
SRC={shlex.quote(iran_ip)}
TABLE={int(table)}
PREF={int(pref)}

cleanup()
{{
    ip -4 rule del pref "$PREF" \
      >/dev/null 2>&1 \
      || true

    ip -4 route flush table "$TABLE" \
      >/dev/null 2>&1 \
      || true
}}

if [ "${{1:-run}}" = "cleanup" ]; then
    cleanup
    exit 0
fi

while true
do
    if ip link show "$IFACE" \
         >/dev/null 2>&1 \
       && \
       ip -4 addr show dev "$IFACE" \
         2>/dev/null \
       | grep -qw "$SRC"
    then
        ip -4 route replace \
          default \
          dev "$IFACE" \
          table "$TABLE" \
          src "$SRC" \
          >/dev/null 2>&1 \
          || true

        ip -4 rule show \
          | grep -Eq \
            "^${{PREF}}:.*from ${{SRC}}(/32)? lookup ${{TABLE}}($| )" \
          || \
          ip -4 rule add \
            pref "$PREF" \
            from "$SRC/32" \
            lookup "$TABLE" \
            >/dev/null 2>&1 \
          || true
    fi

    sleep 2
done
"""

        route_unit = f"""[Unit]
Description=TwinPanel Tunnel {tid} Relay V22 Source Route
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={_route_helper(tid)} run
ExecStop={_route_helper(tid)} cleanup
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
"""

        # ----------------------------------------------------
        # Exit: narrow forwarding + NAT for this Relay subnet.
        #
        # No flushes. No blanket firewall policy changes.
        # Every rule is tunnel-specific and comment-tagged.
        # ----------------------------------------------------

        egress_script = f"""#!/bin/bash
set -u

IFACE={shlex.quote(iface)}
NET={shlex.quote(network)}
TAG=TP-RELAY-{tid}-V22

outdev()
{{
    ip -4 route show default \
      | awk '
        /^default/ {{
            for (i=1; i<=NF; i++) {{
                if ($i == "dev") {{
                    print $(i+1)
                    exit
                }}
            }}
        }}
      '
}}

remove_rules()
{{
    OUT="$(outdev)"

    [ -n "$OUT" ] \
      || return 0

    while \
      iptables \
        -t nat \
        -C POSTROUTING \
        -s "$NET" \
        -o "$OUT" \
        -m comment \
        --comment "$TAG-NAT" \
        -j MASQUERADE \
        2>/dev/null
    do
        iptables \
          -t nat \
          -D POSTROUTING \
          -s "$NET" \
          -o "$OUT" \
          -m comment \
          --comment "$TAG-NAT" \
          -j MASQUERADE \
          >/dev/null 2>&1 \
          || break
    done

    while \
      iptables \
        -C FORWARD \
        -i "$IFACE" \
        -o "$OUT" \
        -s "$NET" \
        -m comment \
        --comment "$TAG-FWD-OUT" \
        -j ACCEPT \
        2>/dev/null
    do
        iptables \
          -D FORWARD \
          -i "$IFACE" \
          -o "$OUT" \
          -s "$NET" \
          -m comment \
          --comment "$TAG-FWD-OUT" \
          -j ACCEPT \
          >/dev/null 2>&1 \
          || break
    done

    while \
      iptables \
        -C FORWARD \
        -i "$OUT" \
        -o "$IFACE" \
        -d "$NET" \
        -m conntrack \
        --ctstate RELATED,ESTABLISHED \
        -m comment \
        --comment "$TAG-FWD-IN" \
        -j ACCEPT \
        2>/dev/null
    do
        iptables \
          -D FORWARD \
          -i "$OUT" \
          -o "$IFACE" \
          -d "$NET" \
          -m conntrack \
          --ctstate RELATED,ESTABLISHED \
          -m comment \
          --comment "$TAG-FWD-IN" \
          -j ACCEPT \
          >/dev/null 2>&1 \
          || break
    done
}}

if [ "${{1:-apply}}" = "cleanup" ]; then
    remove_rules
    exit 0
fi

OUT="$(outdev)"

[ -n "$OUT" ] \
  || exit 41

if [ "$(cat /proc/sys/net/ipv4/ip_forward)" != "1" ]; then
    sysctl -w net.ipv4.ip_forward=1 \
      >/dev/null
fi

iptables \
  -t nat \
  -C POSTROUTING \
  -s "$NET" \
  -o "$OUT" \
  -m comment \
  --comment "$TAG-NAT" \
  -j MASQUERADE \
  2>/dev/null \
|| \
iptables \
  -t nat \
  -I POSTROUTING 1 \
  -s "$NET" \
  -o "$OUT" \
  -m comment \
  --comment "$TAG-NAT" \
  -j MASQUERADE

iptables \
  -C FORWARD \
  -i "$IFACE" \
  -o "$OUT" \
  -s "$NET" \
  -m comment \
  --comment "$TAG-FWD-OUT" \
  -j ACCEPT \
  2>/dev/null \
|| \
iptables \
  -I FORWARD 1 \
  -i "$IFACE" \
  -o "$OUT" \
  -s "$NET" \
  -m comment \
  --comment "$TAG-FWD-OUT" \
  -j ACCEPT

iptables \
  -C FORWARD \
  -i "$OUT" \
  -o "$IFACE" \
  -d "$NET" \
  -m conntrack \
  --ctstate RELATED,ESTABLISHED \
  -m comment \
  --comment "$TAG-FWD-IN" \
  -j ACCEPT \
  2>/dev/null \
|| \
iptables \
  -I FORWARD 1 \
  -i "$OUT" \
  -o "$IFACE" \
  -d "$NET" \
  -m conntrack \
  --ctstate RELATED,ESTABLISHED \
  -m comment \
  --comment "$TAG-FWD-IN" \
  -j ACCEPT

exit 0
"""

        egress_unit = f"""[Unit]
Description=TwinPanel Tunnel {tid} Relay V22 Exit Egress
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart={_egress_helper(tid)} apply
ExecStop={_egress_helper(tid)} cleanup
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""

        await _write(
            ci,
            _route_helper(tid),
            route_script,
            "700",
        )

        await _write(
            ci,
            (
                "/etc/systemd/system/"
                + _route_service(tid)
            ),
            route_unit,
            "644",
        )

        await _write(
            ce,
            _egress_helper(tid),
            egress_script,
            "700",
        )

        await _write(
            ce,
            (
                "/etc/systemd/system/"
                + _egress_service(tid)
            ),
            egress_unit,
            "644",
        )

        await _run(
            ce,
            (
                "systemctl daemon-reload; "
                "systemctl enable "
                f"{shlex.quote(_egress_service(tid))} "
                ">/dev/null; "
                "systemctl restart "
                f"{shlex.quote(_egress_service(tid))}"
            ),
            timeout=25,
        )

        await _run(
            ci,
            (
                "systemctl daemon-reload; "
                "systemctl enable "
                f"{shlex.quote(_route_service(tid))} "
                ">/dev/null; "
                "systemctl restart "
                f"{shlex.quote(_route_service(tid))}"
            ),
            timeout=25,
        )

        # ----------------------------------------------------
        # Verify only that V22 policy plumbing is present here.
        #
        # The manager's authoritative V7/V6 probe remains the
        # final truth for TCP Exit IP + UDP DNS.
        # ----------------------------------------------------

        route_ready = False
        route_text = ""

        for _ in range(10):
            probe = await _run(
                ci,
                (
                    "ip -4 route get "
                    "1.1.1.1 "
                    f"from {shlex.quote(iran_ip)} "
                    "2>&1 || true"
                ),
                check=False,
                timeout=8,
            )

            route_text = (
                (probe.stdout or "")
                + (probe.stderr or "")
            )

            if (
                f"dev {iface}" in route_text
                and
                f"table {table}" in route_text
            ):
                route_ready = True
                break

            await asyncio.sleep(1)

        if not route_ready:
            raise RuntimeError(
                "relay_v22_source_route_not_ready:"
                + route_text[-800:]
            )

        egress_check = await _run(
            ce,
            f"""
OUT="$(
  ip -4 route show default \
  | awk '/^default/ {{for(i=1;i<=NF;i++) if($i=="dev") {{print $(i+1); exit}}}}'
)"

test -n "$OUT"

iptables \
  -t nat \
  -C POSTROUTING \
  -s {shlex.quote(network)} \
  -o "$OUT" \
  -m comment \
  --comment TP-RELAY-{tid}-V22-NAT \
  -j MASQUERADE

iptables \
  -C FORWARD \
  -i {shlex.quote(iface)} \
  -o "$OUT" \
  -s {shlex.quote(network)} \
  -m comment \
  --comment TP-RELAY-{tid}-V22-FWD-OUT \
  -j ACCEPT

iptables \
  -C FORWARD \
  -i "$OUT" \
  -o {shlex.quote(iface)} \
  -d {shlex.quote(network)} \
  -m conntrack \
  --ctstate RELATED,ESTABLISHED \
  -m comment \
  --comment TP-RELAY-{tid}-V22-FWD-IN \
  -j ACCEPT
""",
            check=False,
            timeout=15,
        )

        if egress_check.exit_status != 0:
            raise RuntimeError(
                "relay_v22_exit_egress_policy_not_ready"
            )

        print(
            "[SSHRelayV22] "
            "FULL_EGRESS_POLICY_READY "
            f"tunnel={tid} "
            f"interface={iface} "
            f"source={iran_ip} "
            f"table={table} "
            f"network={network}",
            flush=True,
        )

        return {
            "route_table": table,
            "route_rule_pref": pref,
            "route_service": (
                _route_service(tid)
            ),
            "egress_service": (
                _egress_service(tid)
            ),
            "egress_policy_ready": True,
            "exit_tunnel_ip": exit_ip,
        }

    except Exception:
        await _disable_v22_helpers(
            ci,
            ce,
            tid,
        )
        raise

    finally:
        for conn in (
            ci,
            ce,
        ):
            if conn is not None:
                conn.close()
                await conn.wait_closed()


async def _reuse_existing_carrier_relay(
    tunnel: Tunnel,
    iran: Node,
    exit_node: Node,
    db: Session,
) -> dict | None:
    row = _member(
        db,
        int(tunnel.id),
    )

    if (
        row is None
        or not row.config_text
    ):
        return None

    try:
        cfg = json.loads(
            row.config_text
        )
    except Exception:
        return None

    if not isinstance(
        cfg,
        dict,
    ):
        return None

    mode = str(
        cfg.get("mode")
        or ""
    )

    if mode not in {
        "split_hop_carrier_v21",
        "split_hop_carrier_v22",
    }:
        return None

    try:
        result = await verify_ssh_relay(
            tunnel,
            iran,
            db,
        )
    except Exception:
        return None

    egress = await _install_full_egress_v22(
        tunnel,
        iran,
        exit_node,
        db,
    )

    cfg.update(
        egress
    )

    cfg["mode"] = (
        "split_hop_carrier_v22"
    )

    cfg["egress_version"] = 22

    row.enabled = True
    row.status = "online"
    row.last_error = None
    row.last_healthy_at = (
        datetime.utcnow()
    )
    row.updated_at = (
        datetime.utcnow()
    )

    row.config_text = json.dumps(
        cfg,
        ensure_ascii=False,
    )

    db.commit()

    result.update(
        {
            "mode": (
                "split_hop_carrier_v22"
            ),
            "carrier_tunnel_id": (
                cfg.get(
                    "carrier_tunnel_id"
                )
            ),
            "egress_version": 22,
            **egress,
        }
    )

    print(
        "[SSHRelayV22] "
        "REUSED_EXISTING_CARRIER_RELAY "
        f"tunnel={int(tunnel.id)} "
        "carrier_tunnel="
        f"{cfg.get('carrier_tunnel_id')}",
        flush=True,
    )

    return result


async def provision_ssh_relay_v22(
    tunnel: Tunnel,
    iran: Node,
    relay: Node,
    exit_node: Node,
    db: Session,
) -> dict:
    try:
        reused = (
            await
            _reuse_existing_carrier_relay(
                tunnel,
                iran,
                exit_node,
                db,
            )
        )

        if reused is not None:
            return reused

        result = (
            await
            provision_ssh_relay_v21(
                tunnel,
                iran,
                relay,
                exit_node,
                db,
            )
        )

        # All SSH Relay modes need source-policy routing
        # and final Exit egress policy, not only Carrier V21.

        egress = (
            await
            _install_full_egress_v22(
                tunnel,
                iran,
                exit_node,
                db,
            )
        )

        row = _member(
            db,
            int(tunnel.id),
        )

        if row is None:
            raise RuntimeError(
                "relay_v22_transport_row_missing"
            )

        try:
            cfg = json.loads(
                row.config_text
                or "{}"
            )
        except Exception:
            cfg = {}

        if not isinstance(
            cfg,
            dict,
        ):
            cfg = {}

        old_mode = str(
            cfg.get("mode")
            or result.get("mode")
            or ""
        )

        cfg.update(
            egress
        )

        cfg[
            "egress_version"
        ] = 22

        if (
            old_mode
            == "split_hop_carrier_v21"
        ):
            cfg["mode"] = (
                "split_hop_carrier_v22"
            )
            result["mode"] = (
                "split_hop_carrier_v22"
            )

        row.enabled = True
        row.status = "online"
        row.last_error = None
        row.last_healthy_at = (
            datetime.utcnow()
        )
        row.updated_at = (
            datetime.utcnow()
        )

        row.config_text = json.dumps(
            cfg,
            ensure_ascii=False,
        )

        db.commit()

        result.update(
            {
                "egress_version": 22,
                **egress,
            }
        )

        return result

    except asyncio.CancelledError:
        raise

    except Exception as exc:
        db.rollback()

        row = _member(
            db,
            int(tunnel.id),
        )

        if row is not None:
            row.enabled = False
            row.status = "offline"
            row.last_error = (
                "v22_full_egress_failed:"
                f"{type(exc).__name__}:"
                f"{exc}"
            )[:1800]
            row.updated_at = (
                datetime.utcnow()
            )
            db.commit()

        raise


def apply_carrier_aware_relay_v22() -> None:
    apply_carrier_aware_relay_v21()

    print(
        "TWINPANEL_CARRIER_AWARE_RELAY_V22_ACTIVE "
        "manager_retry=v22 "
        "source_policy_route=1 "
        "exit_forward_nat=1 "
        "carrier_mutation=0",
        flush=True,
    )
