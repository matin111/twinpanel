from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .models import Tunnel, TunnelTransport


# ============================================================
# TWINPANEL MANAGED ARTIFACT PREFLIGHT V1

# Historical runtime reservation.
# Tunnel/relay 30 must never be removed automatically.
TWINPANEL_PROTECTED_LEGACY_TUNNEL_IDS = {
    30,
}
#
# Rules:
#   - Artifacts belonging to a Tunnel still present in DB
#     are NEVER removed.
#   - Only orphan TwinPanel-managed artifacts may be removed.
#   - cleanup=False is a completely read-only dry-run.
# ============================================================


def managed_tunnel_ids_for_node(
    db: Session,
    node_id: int,
) -> list[int]:
    target = int(node_id)

    ids = {
        int(row[0])
        for row in (
            db.query(Tunnel.id)
            .filter(
                (Tunnel.iran_node_id == target)
                | (Tunnel.exit_node_id == target)
            )
            .all()
        )
    }

    relay_rows = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.transport
            == "ssh_relay"
        )
        .all()
    )

    for row in relay_rows:
        if not row.config_text:
            continue

        try:
            cfg = json.loads(
                row.config_text
            )
        except Exception:
            continue

        if not isinstance(cfg, dict):
            continue

        try:
            relay_node_id = int(
                cfg.get("relay_node_id")
                or 0
            )
        except Exception:
            relay_node_id = 0

        if relay_node_id == target:
            ids.add(
                int(row.tunnel_id)
            )

    ids.update(
        TWINPANEL_PROTECTED_LEGACY_TUNNEL_IDS
    )

    return sorted(ids)


REMOTE_PREFLIGHT = r'''
KEEP_IDS="__KEEP_IDS__"
APPLY="__APPLY__"

ERRORS=0


is_keep() {
    ID="$1"

    case " $KEEP_IDS " in
        *" $ID "*)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}


valid_number() {
    case "$1" in
        ""|*[!0-9]*)
            return 1
            ;;
        *)
            return 0
            ;;
    esac
}


iface_owned() {
    NUM="$1"

    if ! valid_number "$NUM"; then
        return 1
    fi

    if is_keep "$NUM"; then
        return 0
    fi

    if [ "$NUM" -ge 100 ]; then
        RELAY_ID=$((NUM - 100))

        if is_keep "$RELAY_ID"; then
            return 0
        fi
    fi

    return 1
}


event() {
    KIND="$1"
    ID="$2"

    if [ "$APPLY" = "1" ]; then
        echo "REMOVED $KIND $ID"
    else
        echo "ORPHAN $KIND $ID"
    fi
}


cleanup_backhaul() {
    ID="$1"

    valid_number "$ID" || return 0
    is_keep "$ID" && return 0

    event "backhaul" "$ID"

    [ "$APPLY" = "1" ] || return 0

    UNIT="twinpanel-backhaul-${ID}.service"
    IFACE="bh${ID}"
    CONFIG="/etc/twinpanel/backhaul/tunnel-${ID}.toml"

    systemctl disable --now "$UNIT" \
        >/dev/null 2>&1 || true

    rm -f \
        "/etc/systemd/system/$UNIT" \
        "/etc/systemd/system/multi-user.target.wants/$UNIT" \
        "$CONFIG"

    ip link del "$IFACE" \
        >/dev/null 2>&1 || true
}


cleanup_ssh() {
    NUM="$1"

    valid_number "$NUM" || return 0

    # Historical production TP27 is protected.
    [ "$NUM" = "27" ] && return 0

    is_keep "$NUM" && return 0

    event "ssh_tunnel" "$NUM"

    [ "$APPLY" = "1" ] || return 0

    IRAN_UNIT="tp${NUM}-ssh.service"
    EXIT_UNIT="tp${NUM}-exit-tun.service"

    systemctl disable --now \
        "$IRAN_UNIT" \
        "$EXIT_UNIT" \
        >/dev/null 2>&1 || true

    rm -f \
        "/etc/systemd/system/$IRAN_UNIT" \
        "/etc/systemd/system/$EXIT_UNIT" \
        "/etc/systemd/system/multi-user.target.wants/$IRAN_UNIT" \
        "/etc/systemd/system/multi-user.target.wants/$EXIT_UNIT" \
        "/usr/local/sbin/tp${NUM}-iran-up" \
        "/usr/local/sbin/tp${NUM}-exit-up"

    rm -rf \
        "/etc/twinpanel/tp${NUM}-ssh"

    userdel -r "tp${NUM}" \
        >/dev/null 2>&1 || true

    if ! iface_owned "$NUM"; then
        ip link del "tun${NUM}" \
            >/dev/null 2>&1 || true
    fi
}


remove_relay_sshd_block() {
    ID="$1"

    [ "$APPLY" = "1" ] || return 0
    [ -f /etc/ssh/sshd_config ] || return 0

    TMP=$(mktemp)

    awk \
      -v BEGIN_MARK="# BEGIN TWINPANEL RELAY $ID" \
      -v END_MARK="# END TWINPANEL RELAY $ID" \
      '
        $0 == BEGIN_MARK {
            SKIP=1
            next
        }

        $0 == END_MARK {
            SKIP=0
            next
        }

        !SKIP {
            print
        }
      ' \
      /etc/ssh/sshd_config \
      > "$TMP"

    if command -v sshd >/dev/null 2>&1; then
        if sshd -t -f "$TMP" \
            >/dev/null 2>&1
        then
            cat "$TMP" \
                > /etc/ssh/sshd_config

            systemctl reload ssh \
                >/dev/null 2>&1 || \
            systemctl reload sshd \
                >/dev/null 2>&1 || true
        else
            echo "ERROR relay_sshd_validation $ID"
            ERRORS=$((ERRORS + 1))
        fi
    else
        cat "$TMP" \
            > /etc/ssh/sshd_config
    fi

    rm -f "$TMP"
}


cleanup_relay() {
    ID="$1"

    valid_number "$ID" || return 0
    is_keep "$ID" && return 0

    event "ssh_relay" "$ID"

    [ "$APPLY" = "1" ] || return 0

    IRAN_UNIT="tp${ID}-relay-ssh.service"
    IRAN_HELPER_UNIT="tp${ID}-relay-if.service"
    EXIT_HELPER_UNIT="tp${ID}-relay-exit-if.service"

    systemctl disable --now \
        "$IRAN_UNIT" \
        "$IRAN_HELPER_UNIT" \
        "$EXIT_HELPER_UNIT" \
        >/dev/null 2>&1 || true

    rm -f \
        "/etc/systemd/system/$IRAN_UNIT" \
        "/etc/systemd/system/$IRAN_HELPER_UNIT" \
        "/etc/systemd/system/$EXIT_HELPER_UNIT" \
        "/etc/systemd/system/multi-user.target.wants/$IRAN_UNIT" \
        "/etc/systemd/system/multi-user.target.wants/$IRAN_HELPER_UNIT" \
        "/etc/systemd/system/multi-user.target.wants/$EXIT_HELPER_UNIT" \
        "/usr/local/sbin/tp${ID}-relay-iran-if" \
        "/usr/local/sbin/tp${ID}-relay-exit-if"

    rm -rf \
        "/etc/twinpanel/ssh-relay/tunnel-${ID}"

    NUM=$((100 + ID))

    if ! iface_owned "$NUM"; then
        ip link del "tun${NUM}" \
            >/dev/null 2>&1 || true
    fi

    if [ -f /root/.ssh/authorized_keys ]; then
        grep -vE \
          "tp${ID}-relay-(hop|exit)$" \
          /root/.ssh/authorized_keys \
          > /root/.ssh/authorized_keys.tp-preflight \
          || true

        cat \
          /root/.ssh/authorized_keys.tp-preflight \
          > /root/.ssh/authorized_keys

        rm -f \
          /root/.ssh/authorized_keys.tp-preflight

        chmod 600 \
          /root/.ssh/authorized_keys
    fi

    remove_relay_sshd_block "$ID"
}


cleanup_mwg() {
    ID="$1"

    valid_number "$ID" || return 0
    is_keep "$ID" && return 0

    event "legacy_wireguard" "$ID"

    [ "$APPLY" = "1" ] || return 0

    ip link del "mwg${ID}" \
        >/dev/null 2>&1 || true

    rm -f \
      "/var/lib/twinpanel-agent/wireguard/${ID}.key" \
      "/var/lib/twinpanel-agent/wireguard/${ID}.pub" \
      "/var/lib/moviline-agent/wireguard/${ID}.key" \
      "/var/lib/moviline-agent/wireguard/${ID}.pub"
}


cleanup_chain() {
    TABLE="$1"
    HOOK="$2"
    CHAIN="$3"
    ID="$4"

    valid_number "$ID" || return 0
    is_keep "$ID" && return 0

    event "iptables:$CHAIN" "$ID"

    [ "$APPLY" = "1" ] || return 0

    while iptables \
        -t "$TABLE" \
        -C "$HOOK" \
        -j "$CHAIN" \
        >/dev/null 2>&1
    do
        iptables \
            -t "$TABLE" \
            -D "$HOOK" \
            -j "$CHAIN" \
            >/dev/null 2>&1 || break
    done

    iptables \
        -t "$TABLE" \
        -F "$CHAIN" \
        >/dev/null 2>&1 || true

    iptables \
        -t "$TABLE" \
        -X "$CHAIN" \
        >/dev/null 2>&1 || true
}


# ============================================================
# Backhaul
# ============================================================

for PATH_ITEM in \
    /etc/systemd/system/twinpanel-backhaul-*.service \
    /etc/systemd/system/multi-user.target.wants/twinpanel-backhaul-*.service
do
    [ -e "$PATH_ITEM" ] || continue

    NAME=$(basename "$PATH_ITEM")
    ID="${NAME#twinpanel-backhaul-}"
    ID="${ID%.service}"

    cleanup_backhaul "$ID"
done


for PATH_ITEM in \
    /etc/twinpanel/backhaul/tunnel-*.toml
do
    [ -e "$PATH_ITEM" ] || continue

    NAME=$(basename "$PATH_ITEM")
    ID="${NAME#tunnel-}"
    ID="${ID%.toml}"

    cleanup_backhaul "$ID"
done


# ============================================================
# SSH Tunnel
# ============================================================

for PATH_ITEM in \
    /etc/systemd/system/tp*-ssh.service \
    /etc/systemd/system/tp*-exit-tun.service \
    /etc/systemd/system/multi-user.target.wants/tp*-ssh.service \
    /etc/systemd/system/multi-user.target.wants/tp*-exit-tun.service
do
    [ -e "$PATH_ITEM" ] || continue

    NAME=$(basename "$PATH_ITEM")

    case "$NAME" in
        tp*-relay-*)
            continue
            ;;
    esac

    ID="${NAME#tp}"
    ID="${ID%-ssh.service}"
    ID="${ID%-exit-tun.service}"

    cleanup_ssh "$ID"
done


for PATH_ITEM in \
    /etc/twinpanel/tp*-ssh \
    /usr/local/sbin/tp*-iran-up \
    /usr/local/sbin/tp*-exit-up
do
    [ -e "$PATH_ITEM" ] || continue

    NAME=$(basename "$PATH_ITEM")

    ID="${NAME#tp}"
    ID="${ID%-ssh}"
    ID="${ID%-iran-up}"
    ID="${ID%-exit-up}"

    cleanup_ssh "$ID"
done


# ============================================================
# SSH Relay
# ============================================================

for PATH_ITEM in \
    /etc/systemd/system/tp*-relay-*.service \
    /etc/systemd/system/multi-user.target.wants/tp*-relay-*.service \
    /usr/local/sbin/tp*-relay-iran-if \
    /usr/local/sbin/tp*-relay-exit-if
do
    [ -e "$PATH_ITEM" ] || continue

    NAME=$(basename "$PATH_ITEM")

    ID="${NAME#tp}"
    ID="${ID%%-relay-*}"

    cleanup_relay "$ID"
done


for PATH_ITEM in \
    /etc/twinpanel/ssh-relay/tunnel-*
do
    [ -e "$PATH_ITEM" ] || continue

    NAME=$(basename "$PATH_ITEM")
    ID="${NAME#tunnel-}"

    cleanup_relay "$ID"
done


# ============================================================
# Legacy WireGuard
# ============================================================

for PATH_ITEM in /sys/class/net/mwg*; do
    [ -e "$PATH_ITEM" ] || continue

    NAME=$(basename "$PATH_ITEM")
    ID="${NAME#mwg}"

    cleanup_mwg "$ID"
done


# ============================================================
# Old per-tunnel firewall chains
# ============================================================

if command -v iptables >/dev/null 2>&1; then

    for CHAIN in $(
        iptables -t nat -S 2>/dev/null |
        awk '
          $1 == "-N" &&
          $2 ~ /^TP_PUBLIC_[0-9]+$/ {
              print $2
          }
        '
    ); do
        ID="${CHAIN#TP_PUBLIC_}"

        cleanup_chain \
            nat \
            PREROUTING \
            "$CHAIN" \
            "$ID"
    done


    for CHAIN in $(
        iptables -t nat -S 2>/dev/null |
        awk '
          $1 == "-N" &&
          $2 ~ /^TP_SNAT_[0-9]+$/ {
              print $2
          }
        '
    ); do
        ID="${CHAIN#TP_SNAT_}"

        cleanup_chain \
            nat \
            POSTROUTING \
            "$CHAIN" \
            "$ID"
    done


    for CHAIN in $(
        iptables -t filter -S 2>/dev/null |
        awk '
          $1 == "-N" &&
          $2 ~ /^TP_FORWARD_[0-9]+$/ {
              print $2
          }
        '
    ); do
        ID="${CHAIN#TP_FORWARD_}"

        cleanup_chain \
            filter \
            FORWARD \
            "$CHAIN" \
            "$ID"
    done

fi


if [ "$APPLY" = "1" ]; then
    rmdir \
      /etc/twinpanel/backhaul \
      >/dev/null 2>&1 || true

    rmdir \
      /etc/twinpanel/ssh-relay \
      >/dev/null 2>&1 || true

    systemctl daemon-reload \
      >/dev/null 2>&1 || true
fi


if [ "$ERRORS" -gt 0 ]; then
    echo "PREFLIGHT_FAILED errors=$ERRORS"
    exit 90
fi


echo "PREFLIGHT_OK keep=$KEEP_IDS apply=$APPLY"
exit 0
'''


async def preflight_managed_artifacts_on_conn(
    conn,
    db: Session,
    node_id: int,
    *,
    cleanup: bool = False,
) -> dict:
    keep_ids = managed_tunnel_ids_for_node(
        db,
        int(node_id),
    )

    keep_text = " ".join(
        str(item)
        for item in keep_ids
    )

    script = (
        REMOTE_PREFLIGHT
        .replace(
            "__KEEP_IDS__",
            keep_text,
        )
        .replace(
            "__APPLY__",
            "1" if cleanup else "0",
        )
    )

    result = await conn.run(
        script,
        check=False,
    )

    stdout = str(
        result.stdout or ""
    ).strip()

    stderr = str(
        result.stderr or ""
    ).strip()

    if result.exit_status != 0:
        raise RuntimeError(
            (
                stdout
                + "\n"
                + stderr
            ).strip()[-3000:]
            or (
                "managed preflight failed "
                f"with exit={result.exit_status}"
            )
        )

    events = []
    seen_events = set()

    for line in stdout.splitlines():
        line = line.strip()

        if not (
            line.startswith("ORPHAN ")
            or line.startswith("REMOVED ")
            or line.startswith("ERROR ")
        ):
            continue

        if line in seen_events:
            continue

        seen_events.add(line)
        events.append(line)

    return {
        "ok": True,
        "node_id": int(node_id),
        "cleanup": bool(cleanup),
        "keep_tunnel_ids": keep_ids,
        "events": events,
    }
