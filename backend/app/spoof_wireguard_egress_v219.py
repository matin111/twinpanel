from __future__ import annotations

import json
import shlex

from sqlalchemy.orm import Session

from . import spoof_reverse_icmp_fallback_v214 as v214
from .transport_candidates import spoof_wg
from .transport_candidates.common import run


# ============================================================
# TWINPANEL SPOOF WIREGUARD EGRESS ALLOWED-IPS V219
#
# Production Tunnel #8 proved the V217 reverse-ICMP path and V218 RPDB policy
# are healthy, but internet egress sourced from the Iran Spoof address still
# fails before any packet reaches tpsp*. The Linux route decision correctly
# selects table 330xx -> tpsp*, while the Iran WireGuard peer only owns the
# Exit /32. WireGuard cryptokey routing therefore rejects internet destinations
# even though the Linux policy route points at the interface.
#
# A bounded production A/B proved the exact cause:
#   * Iran peer AllowedIPs=10.250.x.x/32 -> TCP egress ENETUNREACH;
#   * Iran peer AllowedIPs=0.0.0.0/0 -> TCP + UDP DNS egress PASS;
#   * Exit peer remains the Iran /32.
#
# V219 changes only the Iran Spoof-WG peer cryptokey route. Linux RPDB remains
# source-scoped by V218, so this does not publish a host default route or alter
# TP27/VXLAN. The generated helper is patched as well as the live peer so a
# systemd restart preserves the same contract.
# ============================================================

MARKER = "TWINPANEL_SPOOF_WIREGUARD_EGRESS_V219"
VERSION = 219
IRAN_ALLOWED_IPS = "0.0.0.0/0"

_applied = False
_original_write_peer_runtime_icmp = None
_original_install_icmp = None


async def _write_peer_runtime_icmp_v219(
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
    if _original_write_peer_runtime_icmp is None:
        raise RuntimeError("spoof_v219_original_runtime_writer_missing")

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

    if role != "iran":
        return

    iface = str(rt["interface"])
    exit_ip = str(rt["exit_ip"])
    helper = spoof_wg._helper_path(tunnel_id, role)
    historical = f"allowed-ips {exit_ip}/32"
    replacement = f"allowed-ips {IRAN_ALLOWED_IPS}"

    await run(
        conn,
        f"""
set -e
HELPER={shlex.quote(helper)}
IFACE={shlex.quote(iface)}
PEER={shlex.quote(peer_public_key)}
OLD={shlex.quote(historical)}
NEW={shlex.quote(replacement)}

COUNT="$(grep -F -o "$OLD" "$HELPER" 2>/dev/null | wc -l | tr -d '[:space:]')"
if [ "$COUNT" != "1" ]; then
  echo "unexpected historical AllowedIPs occurrence count: $COUNT" >&2
  exit 71
fi

sed -i "s#$OLD#$NEW#" "$HELPER"
grep -Fq "$NEW" "$HELPER"

wg set "$IFACE" peer "$PEER" allowed-ips {shlex.quote(IRAN_ALLOWED_IPS)}

ACTUAL="$(wg show "$IFACE" allowed-ips | awk -v peer="$PEER" '$1 == peer {{print $2; exit}}')"
if [ "$ACTUAL" != {shlex.quote(IRAN_ALLOWED_IPS)} ]; then
  echo "Iran Spoof WG AllowedIPs verification failed: $ACTUAL" >&2
  exit 72
fi

printf 'V219_IRAN_ALLOWED_IPS=%s helper=%s\\n' "$ACTUAL" "$HELPER"
""",
        "spoof_wg_v219_iran_allowed_ips",
        30,
    )


def _updated_meta(raw: str | None) -> str:
    meta = v214._meta_dict(raw)
    meta["generation"] = VERSION
    meta["qualification"] = "full-shared-l3-probe+reverse-icmp-v219"
    meta["spoof_wireguard_egress"] = {
        "version": VERSION,
        "iran_peer_allowed_ips": IRAN_ALLOWED_IPS,
        "exit_peer_allowed_ips": "iran-inner-ip/32",
        "routing_authority": "v218-source-policy",
        "host_default_route_changed": False,
        "restart_persistence": "generated-helper-patched",
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


async def _install_icmp_v219(
    tunnel_id: int,
    db: Session,
    *,
    trigger: str,
    udp_error: str | None = None,
) -> dict:
    if _original_install_icmp is None:
        raise RuntimeError("spoof_v219_original_icmp_installer_missing")

    result = await _original_install_icmp(
        int(tunnel_id),
        db,
        trigger=trigger,
        udp_error=udp_error,
    )

    row = v214._row(db, int(tunnel_id))
    if row is None:
        raise RuntimeError("spoof_v219_transport_row_missing_after_success")

    row.config_text = _updated_meta(row.config_text)
    db.commit()
    db.refresh(row)

    out = dict(result)
    out.update(
        {
            "generation": VERSION,
            "qualification": "full-shared-l3-probe+reverse-icmp-v219",
            "iran_peer_allowed_ips": IRAN_ALLOWED_IPS,
            "wireguard_egress": True,
        }
    )
    return out


def apply_spoof_wireguard_egress_v219() -> None:
    global _applied
    global _original_write_peer_runtime_icmp
    global _original_install_icmp

    if _applied:
        return

    _original_write_peer_runtime_icmp = v214._write_peer_runtime_icmp
    _original_install_icmp = v214._install_icmp

    # V217 remains the authoritative Iran service/runtime writer; V219 wraps
    # its completed runtime and changes only the WireGuard peer cryptokey route
    # plus the generated helper used by future service restarts.
    v214._write_peer_runtime_icmp = _write_peer_runtime_icmp_v219
    v214._install_icmp = _install_icmp_v219

    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        f"iran_peer_allowed_ips={IRAN_ALLOWED_IPS} "
        "exit_peer_allowed_ips=iran-inner-ip/32 "
        "routing_authority=v218-source-policy "
        "helper_restart_persistence=true "
        "tp27=unchanged vxlan=unchanged shared_probe=v179-unchanged",
        flush=True,
    )
