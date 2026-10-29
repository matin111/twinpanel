from __future__ import annotations

import asyncio
import json
import shlex
import time
from typing import Any

from sqlalchemy.orm import Session

from . import spoof_underlay_guard_v206 as guard
from . import transport_candidates as candidates
from .models import TunnelTransport
from .transport_candidates import spoof_wg
from .transport_candidates.common import (
    close_pair,
    connect_pair,
    copy_binary,
    diag,
    mark,
    prerequisites,
    probe,
    run,
    runtime,
    tunnel_nodes,
)


# ============================================================
# TWINPANEL SPOOF REVERSE ICMP FALLBACK V214
#
# V205 remains the first-choice UDP reverse carrier. Production Tunnel #8
# proved a narrower pair/runtime failure: the real UDP WireGuard response left
# Exit but never appeared on Iran ingress, while the same WG payload delivered
# as ICMP Echo Request reached Iran. V214 therefore adds a bounded, explicit
# ICMP reverse fallback without changing the forward TCP carrier or WireGuard
# L3 dataplane.
#
# V214 is intentionally applied after V206-V213. It may re-qualify only the
# exact V206 reverse-carrier quarantine, or a fresh V205 failure classified by
# that same strict forensic signature. Successful ICMP qualification persists
# the selected reverse carrier and resolves the old guard as historical
# evidence instead of deleting it.
#
# The pinned upstream ICMP receiver temporarily sets the host-global
# net.ipv4.icmp_echo_ignore_all=1. The Iran systemd helper snapshots the prior
# value before start and restores it after every stop/failure so pre-existing
# host policy is not silently overwritten.
# ============================================================

MARKER = "TWINPANEL_SPOOF_REVERSE_ICMP_FALLBACK_V214"
VERSION = 214
ICMP_TRANSPORT = "icmp"
REVERSE_TRANSPORT_META_KEY = "spoof_reverse_transport"
ICMP_RULE_SUFFIX = "ICMP-V214"

_applied = False
_original_install = None
_original_remove_owned_firewall = None


def _row(db: Session, tunnel_id: int) -> TunnelTransport | None:
    return (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == spoof_wg.NAME,
        )
        .first()
    )


def _meta_dict(raw: str | None) -> dict[str, Any]:
    value = spoof_wg._meta_dict(raw)
    return value if isinstance(value, dict) else {}


def _persisted_reverse_transport(raw: str | None) -> str | None:
    value = str(_meta_dict(raw).get(REVERSE_TRANSPORT_META_KEY) or "").strip().lower()
    return value if value == ICMP_TRANSPORT else None


def _icmp_comment(tunnel_id: int) -> str:
    return f"TwinPanel-SPOOF-WG-{int(tunnel_id)}-{ICMP_RULE_SUFFIX}"


def _echo_state_path(tunnel_id: int) -> str:
    return f"/run/twinpanel-spoof-wg-{int(tunnel_id)}-icmp-echo-ignore.prev"


def _exact_quarantine(error: str) -> bool:
    text = str(error or "")
    if guard.classify_spoof_install_failure(text) == guard.UNDERLAY_REASON:
        return True
    return (
        "spoof_underlay_quarantined:" in text
        and guard.UNDERLAY_REASON in text
    )


def _resolved_guard(prior: object, *, now: float) -> dict | None:
    if not isinstance(prior, dict) or not prior:
        return None
    resolved = dict(prior)
    resolved.update(
        {
            "blocked": False,
            "action": "historical_evidence_preserved_icmp_qualified",
            "resolved_at_epoch": now,
            "resolved_by": MARKER,
            "resolved_by_version": VERSION,
        }
    )
    return resolved


def _smart_auto_success_patch(prior_meta: dict[str, Any], *, now: float) -> dict[str, Any]:
    patch: dict[str, Any] = {
        "v214_reverse_icmp_qualified_at_epoch": now,
        "v214_reverse_transport": ICMP_TRANSPORT,
    }
    smart = prior_meta.get("smart_auto_v21")
    if not isinstance(smart, dict):
        return patch
    if str(smart.get("quarantine_reason") or "").strip() != guard.UNDERLAY_REASON:
        return patch
    patch.update(
        {
            "last_probe_epoch": now,
            "last_probe_ok": True,
            "quarantine_reason": "",
            "quarantine_until_epoch": 0.0,
            "stable_seconds": 0.0,
            "stable_since_epoch": now,
        }
    )
    return patch


async def _remove_icmp_firewall(
    ci,
    *,
    tunnel_id: int,
    cfg: dict | None,
) -> None:
    if ci is None or not cfg:
        return
    comment = _icmp_comment(tunnel_id)
    await ci.run(
        f"""
set +e
if command -v iptables >/dev/null 2>&1; then
  while iptables -C INPUT -p icmp --icmp-type echo-request -s {shlex.quote(cfg['exit_spoof_ip'])} -m comment --comment {shlex.quote(comment)} -j ACCEPT 2>/dev/null; do
    iptables -D INPUT -p icmp --icmp-type echo-request -s {shlex.quote(cfg['exit_spoof_ip'])} -m comment --comment {shlex.quote(comment)} -j ACCEPT || break
  done
fi
true
""",
        check=False,
        timeout=30,
    )


async def _remove_owned_firewall_v214(
    ci,
    ce,
    *,
    tunnel_id: int,
    rt: dict,
    cfg: dict | None,
) -> None:
    if _original_remove_owned_firewall is None:
        raise RuntimeError("spoof_v214_original_firewall_cleanup_missing")
    await _remove_icmp_firewall(ci, tunnel_id=int(tunnel_id), cfg=cfg)
    await _original_remove_owned_firewall(
        ci,
        ce,
        tunnel_id=int(tunnel_id),
        rt=rt,
        cfg=cfg,
    )


async def _install_icmp_firewall(
    ci,
    ce,
    *,
    tunnel_id: int,
    rt: dict,
    cfg: dict,
    spoof_source_identifier: int,
) -> None:
    ports = spoof_wg._ports(tunnel_id, spoof_source_identifier)
    icmp_comment = _icmp_comment(tunnel_id)
    exit_comment = f"TwinPanel-SPOOF-WG-{int(tunnel_id)}-EXIT"
    l3_comment = f"TwinPanel-SPOOF-WG-{int(tunnel_id)}-L3"
    ingress_table = spoof_wg._ingress_table(tunnel_id)

    await asyncio.gather(
        run(
            ci,
            f"""
set -e
if command -v nft >/dev/null 2>&1; then
  nft delete table ip {shlex.quote(ingress_table)} >/dev/null 2>&1 || true
fi
if command -v iptables >/dev/null 2>&1; then
  iptables -C INPUT -p icmp --icmp-type echo-request -s {shlex.quote(cfg['exit_spoof_ip'])} -m comment --comment {shlex.quote(icmp_comment)} -j ACCEPT 2>/dev/null || \
  iptables -I INPUT -p icmp --icmp-type echo-request -s {shlex.quote(cfg['exit_spoof_ip'])} -m comment --comment {shlex.quote(icmp_comment)} -j ACCEPT
  iptables -C INPUT -i {shlex.quote(rt['interface'])} -s {shlex.quote(rt['network'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT 2>/dev/null || \
  iptables -I INPUT -i {shlex.quote(rt['interface'])} -s {shlex.quote(rt['network'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT
fi
""",
            "spoof_wg_v214_iran_firewall",
            30,
        ),
        run(
            ce,
            f"""
set -e
if command -v iptables >/dev/null 2>&1; then
  iptables -C INPUT -p tcp --dport {ports['exit_raw_receive_port']} -s {shlex.quote(cfg['iran_spoof_ip'])} -m comment --comment {shlex.quote(exit_comment)} -j ACCEPT 2>/dev/null || \
  iptables -I INPUT -p tcp --dport {ports['exit_raw_receive_port']} -s {shlex.quote(cfg['iran_spoof_ip'])} -m comment --comment {shlex.quote(exit_comment)} -j ACCEPT
  iptables -C INPUT -i {shlex.quote(rt['interface'])} -s {shlex.quote(rt['network'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT 2>/dev/null || \
  iptables -I INPUT -i {shlex.quote(rt['interface'])} -s {shlex.quote(rt['network'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT
  iptables -C FORWARD -i {shlex.quote(rt['interface'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT 2>/dev/null || \
  iptables -I FORWARD -i {shlex.quote(rt['interface'])} -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT
  iptables -C FORWARD -o {shlex.quote(rt['interface'])} -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT 2>/dev/null || \
  iptables -I FORWARD -o {shlex.quote(rt['interface'])} -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment {shlex.quote(l3_comment)} -j ACCEPT
fi
""",
            "spoof_wg_v214_exit_firewall",
            30,
        ),
    )


async def _write_peer_runtime_icmp(
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
    ports = spoof_wg._ports(tunnel_id, spoof_source_identifier)
    helper = spoof_wg._helper_path(tunnel_id, role)
    iface = rt["interface"]

    if role == "iran":
        local_addr = rt["iran_addr"]
        peer_ip = rt["exit_ip"]
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
            f"--recv-transport {ICMP_TRANSPORT}"
        )
        service = rt["iran_service"]
        echo_state = _echo_state_path(tunnel_id)
        echo_up = f"""
ECHO_STATE={shlex.quote(echo_state)}
if [ ! -s "$ECHO_STATE" ]; then
  PREV="$(sysctl -n net.ipv4.icmp_echo_ignore_all 2>/dev/null || printf '0')"
  case "$PREV" in 0|1) ;; *) PREV=0 ;; esac
  printf '%s\n' "$PREV" > "$ECHO_STATE"
  chmod 0600 "$ECHO_STATE"
fi
"""
        echo_down = f"""
ECHO_STATE={shlex.quote(echo_state)}
if [ -s "$ECHO_STATE" ]; then
  PREV="$(cat "$ECHO_STATE" 2>/dev/null || printf '0')"
  case "$PREV" in
    0|1) sysctl -w "net.ipv4.icmp_echo_ignore_all=$PREV" >/dev/null 2>&1 || true ;;
  esac
  rm -f "$ECHO_STATE"
fi
"""
    else:
        local_addr = rt["exit_addr"]
        peer_ip = rt["iran_ip"]
        wg_setup = (
            f'wg set "$IFACE" private-key "$KEY" '
            f"listen-port {ports['exit_wireguard_port']} "
            f"peer {shlex.quote(peer_public_key)} "
            f"allowed-ips {shlex.quote(peer_ip + '/32')}"
        )
        exec_start = (
            f"{spoof_wg.REMOTE_BINARY} remote "
            f"--listen-port {ports['exit_raw_receive_port']} "
            f"--forward 127.0.0.1:{ports['exit_wireguard_port']} "
            f"--client-ip {shlex.quote(iran_public)} "
            f"--client-port {ports['iran_reverse_public_port']} "
            f"--spoof-ip {shlex.quote(cfg['exit_spoof_ip'])} "
            f"--spoof-port {ports['spoof_source_port']} "
            f"--peer-spoof-ip {shlex.quote(cfg['iran_spoof_ip'])} "
            f"--send-transport {ICMP_TRANSPORT} "
            f"--recv-transport {spoof_wg.SEND_TRANSPORT}"
        )
        service = rt["exit_service"]
        echo_up = ""
        echo_down = ""

    helper_text = f"""#!/bin/bash
set -Eeuo pipefail
ACTION="${{1:-up}}"
IFACE={shlex.quote(iface)}
KEY={shlex.quote(private_key_path)}

if [ "$ACTION" = "down" ]; then
{echo_down}
  ip link del "$IFACE" >/dev/null 2>&1 || true
  exit 0
fi

{echo_up}
ip link del "$IFACE" >/dev/null 2>&1 || true
ip link add "$IFACE" type wireguard
{wg_setup}
ip addr replace {shlex.quote(local_addr)} dev "$IFACE"
ip link set dev "$IFACE" mtu {spoof_wg.MTU} up
sysctl -w "net.ipv4.conf.$IFACE.rp_filter=2" >/dev/null 2>&1 || true
"""
    unit = f"""[Unit]
Description=TwinPanel Spoof WG {int(tunnel_id)} {role} V214
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=root
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
cat > {shlex.quote(helper)} <<'EOF'
{helper_text}EOF
chmod 0755 {shlex.quote(helper)}
cat > /etc/systemd/system/{shlex.quote(service)} <<'EOF'
{unit}EOF
systemctl daemon-reload
systemctl enable {shlex.quote(service)} >/dev/null
systemctl restart {shlex.quote(service)}
""",
        f"spoof_wg_v214_{role}_install",
        60,
    )


async def _install_icmp(
    tunnel_id: int,
    db: Session,
    *,
    trigger: str,
    udp_error: str | None = None,
) -> dict:
    _, iran, exit_node = tunnel_nodes(db, tunnel_id)
    rt = dict(runtime(spoof_wg.NAME, tunnel_id))
    rt["tunnel_id"] = int(tunnel_id)

    row = _row(db, tunnel_id)
    raw_config = getattr(row, "config_text", None)
    prior_meta = _meta_dict(raw_config)
    cfg = spoof_wg.configuration_from_text(raw_config)
    if cfg is None:
        raise RuntimeError("spoof_wg_configuration_required")

    identifier_candidates = spoof_wg._source_port_candidates(raw_config)
    persisted_identifier = spoof_wg._persisted_source_port(raw_config)
    artifact_path, artifact_sha = spoof_wg._artifact()
    prior_guard = prior_meta.get("spoof_underlay_guard_v206")

    icmp_cfg = dict(cfg)
    icmp_cfg["recv_transport"] = ICMP_TRANSPORT

    meta: dict[str, Any] = {
        **rt,
        "generation": VERSION,
        "carrier_class": "spoof-mutual-ip-wireguard-l3",
        "depends_on": "wireguard",
        "mtu": spoof_wg.MTU,
        "ports": spoof_wg._ports(tunnel_id, identifier_candidates[0]),
        "spoof_config": icmp_cfg,
        "spoof_source_port_candidates": list(spoof_wg.SPOOF_SOURCE_PORT_CANDIDATES),
        REVERSE_TRANSPORT_META_KEY: ICMP_TRANSPORT,
        "reverse_transport_trigger": trigger,
        "reverse_ingress": {
            "mode": "raw-icmp-echo-request",
            "peer_selector": "exit-spoof-ip",
            "public_udp_port": None,
            "v205_nft_required": False,
            "spoof_port_semantics": "icmp-identifier",
            "upstream_client_port_ignored_for_icmp": spoof_wg.REVERSE_INGRESS_PORT,
        },
        "icmp_echo_reply_suppression": {
            "upstream_behavior": "host-global-while-iran-receiver-active",
            "sysctl": "net.ipv4.icmp_echo_ignore_all",
            "active_value": 1,
            "restore": "systemd-helper-restores-preexisting-value",
        },
        "upstream_version": spoof_wg.UPSTREAM_VERSION,
        "upstream_source_sha": spoof_wg.UPSTREAM_SOURCE_SHA,
        "artifact_sha256": artifact_sha,
        "xdp": False,
    }
    if isinstance(prior_guard, dict) and prior_guard:
        meta["spoof_underlay_guard_v206"] = dict(prior_guard)
    if persisted_identifier is not None:
        meta[spoof_wg.SPOOF_SOURCE_PORT_META_KEY] = persisted_identifier
    if udp_error:
        meta["v214_udp_trigger_error"] = str(udp_error)[-3000:]

    mark(
        db,
        tunnel_id,
        spoof_wg.NAME,
        status="installing",
        meta=json.dumps(meta, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
    )

    ci = ce = None
    try:
        ci, ce = await connect_pair(iran, exit_node, db)
        await asyncio.gather(prerequisites(ci), prerequisites(ce))
        await asyncio.gather(
            spoof_wg._ensure_wireguard(ci),
            spoof_wg._ensure_wireguard(ce),
        )
        await asyncio.gather(
            copy_binary(ci, str(artifact_path), spoof_wg.REMOTE_BINARY),
            copy_binary(ce, str(artifact_path), spoof_wg.REMOTE_BINARY),
        )

        iran_key_path = spoof_wg._key_path(tunnel_id, "iran")
        exit_key_path = spoof_wg._key_path(tunnel_id, "exit")
        (iran_private, iran_public_key), (exit_private, exit_public_key) = await asyncio.gather(
            spoof_wg._keypair(ci, iran_key_path),
            spoof_wg._keypair(ce, exit_key_path),
        )
        _ = iran_private, exit_private

        health = None
        selected_identifier = None
        identifier_attempts: list[int] = []

        for index, identifier in enumerate(identifier_candidates):
            identifier_attempts.append(identifier)
            await spoof_wg._reset_pair(ci, ce, rt, cfg)
            await _install_icmp_firewall(
                ci,
                ce,
                tunnel_id=int(tunnel_id),
                rt=rt,
                cfg=cfg,
                spoof_source_identifier=identifier,
            )
            await _write_peer_runtime_icmp(
                ce,
                role="exit",
                tunnel_id=int(tunnel_id),
                rt=rt,
                private_key_path=exit_key_path,
                peer_public_key=iran_public_key,
                cfg=cfg,
                iran_public=str(iran.public_ip),
                exit_public=str(exit_node.public_ip),
                spoof_source_identifier=identifier,
            )
            await asyncio.sleep(1.0)
            await _write_peer_runtime_icmp(
                ci,
                role="iran",
                tunnel_id=int(tunnel_id),
                rt=rt,
                private_key_path=iran_key_path,
                peer_public_key=exit_public_key,
                cfg=cfg,
                iran_public=str(iran.public_ip),
                exit_public=str(exit_node.public_ip),
                spoof_source_identifier=identifier,
            )
            await asyncio.sleep(5.0)

            try:
                health = await probe(
                    ci,
                    ce,
                    name=spoof_wg.NAME,
                    tunnel_id=int(tunnel_id),
                    rt=rt,
                )
            except RuntimeError as exc:
                has_fallback = index + 1 < len(identifier_candidates)
                if not str(exc).startswith("peer_ping_failed:") or not has_fallback:
                    raise
                continue

            selected_identifier = identifier
            break

        if health is None or selected_identifier is None:
            raise RuntimeError("spoof_wg_v214_icmp_qualification_failed")

        now = time.time()
        final_meta: dict[str, Any] = {
            **meta,
            **health,
            "ports": spoof_wg._ports(tunnel_id, selected_identifier),
            spoof_wg.SPOOF_SOURCE_PORT_META_KEY: selected_identifier,
            "spoof_icmp_identifier": selected_identifier,
            "spoof_icmp_identifier_attempts": identifier_attempts,
            REVERSE_TRANSPORT_META_KEY: ICMP_TRANSPORT,
            "reverse_ingress": {
                "mode": "raw-icmp-echo-request",
                "peer_selector": "exit-spoof-ip",
                "public_udp_port": None,
                "v205_nft_required": False,
                "spoof_port_semantics": "icmp-identifier",
                "upstream_client_port_ignored_for_icmp": spoof_wg.REVERSE_INGRESS_PORT,
            },
            "wireguard": True,
            "qualification": "full-shared-l3-probe+reverse-icmp-v214",
            "smart_auto_v21": _smart_auto_success_patch(prior_meta, now=now),
        }
        resolved = _resolved_guard(prior_guard, now=now)
        if resolved is not None:
            final_meta["spoof_underlay_guard_v206"] = resolved

        mark(
            db,
            tunnel_id,
            spoof_wg.NAME,
            status="online",
            latency_ms=health["latency_ms"],
            meta=json.dumps(
                final_meta,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
        return {
            "ok": True,
            "transport": spoof_wg.NAME,
            "runtime": rt,
            "probe": health,
            "reverse_transport": ICMP_TRANSPORT,
            "spoof_icmp_identifier": selected_identifier,
            "icmp_identifier_attempts": identifier_attempts,
            "fallback_trigger": trigger,
            "upstream_version": spoof_wg.UPSTREAM_VERSION,
            "xdp": False,
        }
    except Exception as exc:
        iran_diag = (
            await diag(ci, rt["iran_service"], rt["interface"])
            if ci
            else ""
        )
        exit_diag = (
            await diag(ce, rt["exit_service"], rt["interface"])
            if ce
            else ""
        )
        sysctl_diag = ""
        if ci is not None:
            result = await ci.run(
                "printf 'icmp_echo_ignore_all='; "
                "sysctl -n net.ipv4.icmp_echo_ignore_all 2>/dev/null || true",
                check=False,
                timeout=15,
            )
            sysctl_diag = (result.stdout or "").strip()
        message = (
            f"reverse_icmp_v214_failed:{type(exc).__name__}: {exc} | "
            f"trigger={trigger} | iran={iran_diag[-1800:]} | "
            f"exit={exit_diag[-1800:]} | sysctl={sysctl_diag[-300:]}"
        )
        if ci is not None and ce is not None:
            try:
                await spoof_wg._reset_pair(ci, ce, rt, cfg)
            except Exception:
                pass
        mark(db, tunnel_id, spoof_wg.NAME, status="failed", error=message)
        raise RuntimeError(message) from exc
    finally:
        await close_pair(ci, ce)


async def _install_v214(tunnel_id: int, db: Session) -> dict:
    if _original_install is None:
        raise RuntimeError("spoof_v214_original_installer_missing")

    row = _row(db, tunnel_id)
    raw = getattr(row, "config_text", None)

    if _persisted_reverse_transport(raw) == ICMP_TRANSPORT:
        return await _install_icmp(
            int(tunnel_id),
            db,
            trigger="persisted_icmp_v214",
        )

    active = guard.active_underlay_quarantine_for_tunnel(db, int(tunnel_id))
    if (
        isinstance(active, dict)
        and active.get("blocked") is True
        and str(active.get("reason") or "") == guard.UNDERLAY_REASON
    ):
        return await _install_icmp(
            int(tunnel_id),
            db,
            trigger="active_v206_v213_udp_quarantine",
        )

    try:
        return await _original_install(int(tunnel_id), db)
    except RuntimeError as exc:
        message = str(exc)
        if not _exact_quarantine(message):
            raise
        return await _install_icmp(
            int(tunnel_id),
            db,
            trigger="fresh_v205_udp_reverse_failure",
            udp_error=message,
        )


def apply_spoof_reverse_icmp_fallback_v214() -> None:
    global _applied, _original_install, _original_remove_owned_firewall
    if _applied:
        return

    installer = candidates.INSTALLERS.get(spoof_wg.NAME)
    if installer is None:
        raise RuntimeError("spoof_v214_installer_missing")

    _original_install = installer
    _original_remove_owned_firewall = spoof_wg._remove_owned_firewall

    # Permanent additive cleanup hook: every later reset removes a stale V214
    # ICMP rule before applying the historical V205 cleanup. No UDP rule is
    # widened or rewritten.
    spoof_wg._remove_owned_firewall = _remove_owned_firewall_v214

    # Apply after V206-V213 so this wrapper can re-qualify the exact old UDP
    # underlay quarantine via ICMP, while all non-matching failures still flow
    # through the existing fail-closed guard unchanged.
    candidates.INSTALLERS[spoof_wg.NAME] = _install_v214
    spoof_wg.install = _install_v214

    _applied = True
    print(
        f"{MARKER}_ACTIVE "
        "udp_v205=first_choice "
        "icmp=exact-underlay-fallback "
        "forward=tcp wireguard_l3=unchanged "
        "v205_nft=disabled_in_icmp_mode "
        "guard_evidence=preserved "
        "icmp_echo_sysctl=prestate-restored-on-stop",
        flush=True,
    )
