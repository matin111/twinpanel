from __future__ import annotations

import json
import shlex
from typing import Any

from sqlalchemy.orm import Session

from . import spoof_reverse_icmp_fallback_v214 as v214
from .transport_candidates import spoof_wg
from .transport_candidates.common import run


# ============================================================
# TWINPANEL SPOOF ICMP SCOPED ECHO SUPPRESSION V217
#
# Production Tunnel #8 proved the reverse ICMP carrier and WireGuard delivery
# are healthy while Exit->Iran inner ICMP Echo Request reaches the Iran WG
# interface and receives no kernel Echo Reply. The pinned upstream local relay
# suppresses ICMP Echo Reply host-wide with:
#
#   net.ipv4.icmp_echo_ignore_all=1
#
# That global knob also suppresses the inner tpsp* health ping. V217 preserves
# V214's exact reverse-ICMP fallback and replaces only that host-global runtime
# side effect for the Iran receiver:
#
#   * install a Spoof-owned OUTPUT drop for outer Echo Reply packets to the
#     configured Exit spoof IP;
#   * run the pinned upstream binary with a per-service sysctl shim that no-ops
#     only writes to net.ipv4.icmp_echo_ignore_all;
#   * keep the pre-existing host sysctl value authoritative and restore it on
#     stop through V214's existing helper state file;
#   * keep the shared V179 L3 probe unchanged, so TP27/VXLAN policy is untouched;
#   * keep V205 UDP first-choice behavior and all V206-V214 guard semantics.
# ============================================================

MARKER = "TWINPANEL_SPOOF_ICMP_SCOPED_ECHO_V217"
VERSION = 217
RULE_SUFFIX = "ICMP-SCOPED-V217"

_applied = False
_original_install_icmp_firewall = None
_original_remove_icmp_firewall = None
_original_write_peer_runtime_icmp = None
_original_install_icmp = None


def _comment(tunnel_id: int) -> str:
    return f"TwinPanel-SPOOF-WG-{int(tunnel_id)}-{RULE_SUFFIX}"


def _shim_dir(tunnel_id: int) -> str:
    return f"/opt/twinpanel/transport/spoof-wg-{int(tunnel_id)}-v217-bin"


def _shim_path(tunnel_id: int) -> str:
    return f"{_shim_dir(tunnel_id)}/sysctl"


def _real_sysctl_shell() -> str:
    return r"""
REAL_SYSCTL=""
for CAND in /usr/sbin/sysctl /sbin/sysctl /usr/bin/sysctl /bin/sysctl; do
  if [ -x "$CAND" ]; then
    REAL_SYSCTL="$CAND"
    break
  fi
done
if [ -z "$REAL_SYSCTL" ]; then
  echo "real sysctl not found" >&2
  exit 70
fi
""".strip()


def _shim_text() -> str:
    return r"""#!/bin/sh
set -eu

if [ "${1:-}" = "-w" ]; then
  case "${2:-}" in
    net.ipv4.icmp_echo_ignore_all=0|net.ipv4.icmp_echo_ignore_all=1)
      # V217 owns ICMP Echo Reply suppression with an exact OUTPUT rule.
      # Return success so the pinned upstream binary keeps its lifecycle
      # contract without changing the host-global echo policy.
      exit 0
      ;;
  esac
fi

for REAL in /usr/sbin/sysctl /sbin/sysctl /usr/bin/sysctl /bin/sysctl; do
  if [ -x "$REAL" ]; then
    exec "$REAL" "$@"
  fi
done

exit 127
"""


async def _install_icmp_firewall_v217(
    ci,
    ce,
    *,
    tunnel_id: int,
    rt: dict,
    cfg: dict,
    spoof_source_identifier: int,
) -> None:
    if _original_install_icmp_firewall is None:
        raise RuntimeError("spoof_v217_original_firewall_install_missing")

    await _original_install_icmp_firewall(
        ci,
        ce,
        tunnel_id=int(tunnel_id),
        rt=rt,
        cfg=cfg,
        spoof_source_identifier=int(spoof_source_identifier),
    )

    comment = _comment(tunnel_id)

    await run(
        ci,
        f"""
set -e
if command -v iptables >/dev/null 2>&1; then
  iptables -C OUTPUT \
    -p icmp --icmp-type echo-reply \
    -d {shlex.quote(cfg['exit_spoof_ip'])} \
    -m comment --comment {shlex.quote(comment)} \
    -j DROP 2>/dev/null || \
  iptables -I OUTPUT 1 \
    -p icmp --icmp-type echo-reply \
    -d {shlex.quote(cfg['exit_spoof_ip'])} \
    -m comment --comment {shlex.quote(comment)} \
    -j DROP
fi
""",
        "spoof_wg_v217_iran_scoped_echo_firewall",
        30,
    )


async def _remove_icmp_firewall_v217(
    ci,
    *,
    tunnel_id: int,
    cfg: dict | None,
) -> None:
    if ci is not None and cfg:
        comment = _comment(tunnel_id)
        await ci.run(
            f"""
set +e
if command -v iptables >/dev/null 2>&1; then
  while iptables -C OUTPUT \
    -p icmp --icmp-type echo-reply \
    -d {shlex.quote(cfg['exit_spoof_ip'])} \
    -m comment --comment {shlex.quote(comment)} \
    -j DROP 2>/dev/null; do
    iptables -D OUTPUT \
      -p icmp --icmp-type echo-reply \
      -d {shlex.quote(cfg['exit_spoof_ip'])} \
      -m comment --comment {shlex.quote(comment)} \
      -j DROP || break
  done
fi
rm -rf {shlex.quote(_shim_dir(tunnel_id))}
true
""",
            check=False,
            timeout=30,
        )

    if _original_remove_icmp_firewall is None:
        raise RuntimeError("spoof_v217_original_firewall_cleanup_missing")

    await _original_remove_icmp_firewall(
        ci,
        tunnel_id=int(tunnel_id),
        cfg=cfg,
    )


async def _write_peer_runtime_icmp_v217(
    conn,
    *,
    role: str,
    tunnel_id: int,
    rt: dict,
    private_key_path: str,
    peer_public_key: str,
    cfg: dict,
    iran_public: str,
    exit_public: str,
    spoof_source_identifier: int,
) -> None:
    if role != "iran":
        if _original_write_peer_runtime_icmp is None:
            raise RuntimeError("spoof_v217_original_runtime_writer_missing")
        await _original_write_peer_runtime_icmp(
            conn,
            role=role,
            tunnel_id=int(tunnel_id),
            rt=rt,
            private_key_path=private_key_path,
            peer_public_key=peer_public_key,
            cfg=cfg,
            iran_public=iran_public,
            exit_public=exit_public,
            spoof_source_identifier=int(spoof_source_identifier),
        )
        return

    ports = spoof_wg._ports(tunnel_id, spoof_source_identifier)
    helper = spoof_wg._helper_path(tunnel_id, role)
    iface = rt["interface"]
    local_addr = rt["iran_addr"]
    peer_ip = rt["exit_ip"]
    service = rt["iran_service"]
    echo_state = v214._echo_state_path(tunnel_id)
    shim_dir = _shim_dir(tunnel_id)
    shim_path = _shim_path(tunnel_id)

    wg_setup = (
        f'wg set "$IFACE" private-key "$KEY" listen-port 0 '
        f"peer {shlex.quote(peer_public_key)} "
        f"allowed-ips {shlex.quote(peer_ip + '/32')} "
        f"endpoint 127.0.0.1:{ports['iran_local_relay_port']} "
        "persistent-keepalive 5"
    )

    exec_start = (
        f"{spoof_wg.REMOTE_BINARY} local "
        f"--listen 127.0.0.1:{ports['iran_local_relay_port']} "
        f"--remote {shlex.quote(exit_public)} "
        f"--remote-port {ports['exit_raw_receive_port']} "
        f"--recv-port {ports['iran_raw_receive_port']} "
        f"--spoof-ip {shlex.quote(cfg['iran_spoof_ip'])} "
        f"--spoof-port {ports['spoof_source_port']} "
        f"--peer-spoof-ip {shlex.quote(cfg['exit_spoof_ip'])} "
        f"--send-transport {spoof_wg.SEND_TRANSPORT} "
        f"--recv-transport {v214.ICMP_TRANSPORT}"
    )

    real_sysctl = _real_sysctl_shell()

    helper_text = f"""#!/bin/bash
set -Eeuo pipefail
ACTION="${{1:-up}}"
IFACE={shlex.quote(iface)}
KEY={shlex.quote(private_key_path)}
ECHO_STATE={shlex.quote(echo_state)}

{real_sysctl}

if [ "$ACTION" = "down" ]; then
  if [ -s "$ECHO_STATE" ]; then
    PREV="$(cat "$ECHO_STATE" 2>/dev/null || printf '0')"
    case "$PREV" in
      0|1) "$REAL_SYSCTL" -w "net.ipv4.icmp_echo_ignore_all=$PREV" >/dev/null 2>&1 || true ;;
    esac
    rm -f "$ECHO_STATE"
  fi
  ip link del "$IFACE" >/dev/null 2>&1 || true
  exit 0
fi

if [ ! -s "$ECHO_STATE" ]; then
  PREV="$("$REAL_SYSCTL" -n net.ipv4.icmp_echo_ignore_all 2>/dev/null || printf '0')"
  case "$PREV" in 0|1) ;; *) PREV=0 ;; esac
  printf '%s\\n' "$PREV" > "$ECHO_STATE"
  chmod 0600 "$ECHO_STATE"
fi

ip link del "$IFACE" >/dev/null 2>&1 || true
ip link add "$IFACE" type wireguard
{wg_setup}
ip addr replace {shlex.quote(local_addr)} dev "$IFACE"
ip link set dev "$IFACE" mtu {spoof_wg.MTU} up
"$REAL_SYSCTL" -w "net.ipv4.conf.$IFACE.rp_filter=2" >/dev/null 2>&1 || true
"""

    shim_text = _shim_text()

    unit = f"""[Unit]
Description=TwinPanel Spoof WG {int(tunnel_id)} {role} V217
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=root
Environment=PATH={shlex.quote(shim_dir)}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStartPre={helper} up
ExecStart={exec_start}
ExecStopPost={helper} down
Restart=always
RestartSec=2
TimeoutStopSec=10
LimitNOFILE=1048576
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_RAW
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
"""

    await run(
        conn,
        f"""
set -e
install -d -m 0755 /opt/twinpanel/transport
install -d -m 0755 {shlex.quote(shim_dir)}

cat > {shlex.quote(shim_path)} <<'EOF'
{shim_text}EOF
chmod 0755 {shlex.quote(shim_path)}

cat > {shlex.quote(helper)} <<'EOF'
{helper_text}EOF
chmod 0755 {shlex.quote(helper)}

cat > /etc/systemd/system/{shlex.quote(service)} <<'EOF'
{unit}EOF

systemctl daemon-reload
systemctl enable {shlex.quote(service)} >/dev/null
systemctl restart {shlex.quote(service)}

PREV="$(cat {shlex.quote(echo_state)} 2>/dev/null || printf 'unknown')"
CUR="$(/usr/sbin/sysctl -n net.ipv4.icmp_echo_ignore_all 2>/dev/null || /sbin/sysctl -n net.ipv4.icmp_echo_ignore_all 2>/dev/null || true)"
printf 'V217_ECHO_PRESTATE=%s V217_ECHO_CURRENT=%s\\n' "$PREV" "$CUR"
""",
        "spoof_wg_v217_iran_install",
        60,
    )


def _updated_meta(raw: str | None) -> str:
    meta = v214._meta_dict(raw)
    meta["generation"] = VERSION
    meta["qualification"] = "full-shared-l3-probe+reverse-icmp-v217"
    meta["icmp_echo_reply_suppression"] = {
        "mode": "scoped-outer-echo-reply-drop",
        "version": VERSION,
        "rule_scope": "icmp-echo-reply-to-exit-spoof-ip",
        "upstream_global_sysctl_write": "service-local-shim-noop",
        "host_sysctl_authority": "preexisting-value-preserved",
        "restore": "v214-systemd-helper-prestate",
    }

    guard = meta.get("spoof_underlay_guard_v206")
    if isinstance(guard, dict) and guard.get("blocked") is False:
        updated_guard = dict(guard)
        updated_guard["resolved_by"] = MARKER
        updated_guard["resolved_by_version"] = VERSION
        meta["spoof_underlay_guard_v206"] = updated_guard

    return json.dumps(
        meta,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


async def _install_icmp_v217(
    tunnel_id: int,
    db: Session,
    *,
    trigger: str,
    udp_error: str | None = None,
) -> dict:
    if _original_install_icmp is None:
        raise RuntimeError("spoof_v217_original_icmp_installer_missing")

    result = await _original_install_icmp(
        int(tunnel_id),
        db,
        trigger=trigger,
        udp_error=udp_error,
    )

    row = v214._row(db, int(tunnel_id))
    if row is None:
        raise RuntimeError("spoof_v217_transport_row_missing_after_success")

    row.config_text = _updated_meta(row.config_text)
    db.commit()
    db.refresh(row)

    out = dict(result)
    out.update(
        {
            "generation": VERSION,
            "qualification": "full-shared-l3-probe+reverse-icmp-v217",
            "icmp_echo_reply_suppression": "scoped-outer-echo-reply-drop",
        }
    )
    return out


def apply_spoof_icmp_scoped_echo_v217() -> None:
    global _applied
    global _original_install_icmp_firewall
    global _original_remove_icmp_firewall
    global _original_write_peer_runtime_icmp
    global _original_install_icmp

    if _applied:
        return

    _original_install_icmp_firewall = v214._install_icmp_firewall
    _original_remove_icmp_firewall = v214._remove_icmp_firewall
    _original_write_peer_runtime_icmp = v214._write_peer_runtime_icmp
    _original_install_icmp = v214._install_icmp

    v214._install_icmp_firewall = _install_icmp_firewall_v217
    v214._remove_icmp_firewall = _remove_icmp_firewall_v217
    v214._write_peer_runtime_icmp = _write_peer_runtime_icmp_v217
    v214._install_icmp = _install_icmp_v217

    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        "scope=spoof-icmp-iran-only "
        "outer_echo_reply=scoped-drop "
        "upstream_echo_sysctl=service-local-shim "
        "host_echo_policy=preserved "
        "shared_probe=v179-unchanged "
        "tp27=unchanged vxlan=unchanged",
        flush=True,
    )
