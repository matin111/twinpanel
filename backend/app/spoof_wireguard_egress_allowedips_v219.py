from __future__ import annotations

import json
import shlex

from sqlalchemy.orm import Session

from . import spoof_reverse_icmp_fallback_v214 as v214
from .transport_candidates import spoof_wg
from .transport_candidates.common import run


MARKER = "TWINPANEL_SPOOF_WIREGUARD_EGRESS_ALLOWEDIPS_V219"
VERSION = 219
IRAN_EGRESS_ALLOWED_IPS = "0.0.0.0/0"
HELPER_MARKER = "TWINPANEL_SPOOF_WG_ALLOWED_IPS_V219"

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
    helper = spoof_wg._helper_path(tunnel_id, role)
    peer = shlex.quote(peer_public_key)
    allowed = shlex.quote(IRAN_EGRESS_ALLOWED_IPS)
    marker = shlex.quote(HELPER_MARKER)

    await run(
        conn,
        f"""
set -e
HELPER={shlex.quote(helper)}
PEER={peer}
EXPECTED={allowed}
if ! grep -Fq {marker} "$HELPER" 2>/dev/null; then
  cat >> "$HELPER" <<'EOF'
# {HELPER_MARKER}
wg set "$IFACE" peer {peer} allowed-ips {allowed}
EOF
fi

wg set {shlex.quote(iface)} peer "$PEER" allowed-ips "$EXPECTED"
ACTUAL="$(wg show {shlex.quote(iface)} allowed-ips 2>/dev/null | awk -v peer="$PEER" '$1 == peer {{ print $2; exit }}')"
if [ "$ACTUAL" != "$EXPECTED" ]; then
  echo "V219_ALLOWED_IPS_MISMATCH actual=$ACTUAL expected=$EXPECTED" >&2
  exit 72
fi
printf 'V219_ALLOWED_IPS=%s\\n' "$ACTUAL"
""",
        "spoof_wg_v219_iran_allowedips",
        30,
    )


def _updated_meta(raw: str | None) -> str:
    meta = v214._meta_dict(raw)
    meta["generation"] = VERSION
    meta["qualification"] = "full-shared-l3-probe+reverse-icmp-v219"
    meta["spoof_wireguard_egress_allowed_ips"] = {
        "version": VERSION,
        "iran_peer_allowed_ips": IRAN_EGRESS_ALLOWED_IPS,
        "exit_peer_allowed_ips": "iran-inner-/32",
        "routing_authority": "v218-source-policy-before-main",
        "scope": "spoof-icmp-iran-peer-only",
        "service_restart_persistence": "v217-helper-extension",
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
            "iran_peer_allowed_ips": IRAN_EGRESS_ALLOWED_IPS,
        }
    )
    return out


def apply_spoof_wireguard_egress_allowedips_v219() -> None:
    global _applied
    global _original_write_peer_runtime_icmp
    global _original_install_icmp

    if _applied:
        return

    _original_write_peer_runtime_icmp = v214._write_peer_runtime_icmp
    _original_install_icmp = v214._install_icmp

    v214._write_peer_runtime_icmp = _write_peer_runtime_icmp_v219
    v214._install_icmp = _install_icmp_v219

    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        f"iran_peer_allowed_ips={IRAN_EGRESS_ALLOWED_IPS} "
        "exit_peer=/32 "
        "routing_authority=v218-source-policy "
        "service_restart=persistent-helper-extension "
        "tp27=unchanged vxlan=unchanged shared_probe=v179-unchanged",
        flush=True,
    )
