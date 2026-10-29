from __future__ import annotations

import json
import shlex
from typing import Any

from sqlalchemy.orm import Session

from . import spoof_reverse_icmp_fallback_v214 as v214
from . import transport_candidates as candidates
from .transport_candidates import common as candidate_common


# ============================================================
# TWINPANEL SPOOF POLICY-RULE PRIORITY V218
#
# Production Tunnel #8 proved that the Spoof /30 peer is healthy in both
# directions, but TCP egress bound to the Iran Spoof address never enters the
# tpsp interface. The historical Spoof RPDB rule used priority 33000+slot,
# which is evaluated after Linux's built-in `main` rule at priority 32766.
# Consequently the node's normal main-table default route wins first.
#
# V218 keeps the historical route-table namespace (33000+slot) intact, but
# moves only the Spoof source-rule priority into a dedicated pre-main band
# (28000-28899). TP27 remains 29000-29899 and kernel IPIP/VXLAN keep their
# existing V209 bands. A stale legacy 330xx rule is removed before every Spoof
# ICMP qualification so old failed attempts do not leave residue.
# ============================================================

MARKER = "TWINPANEL_SPOOF_POLICY_RULE_PRIORITY_V218"
VERSION = 218

SPOOF_POLICY_SPAN = 900
SPOOF_TABLE_BASE = 33000
SPOOF_RULE_BASE = 28000
LINUX_MAIN_RULE_PRIORITY = 32766

_applied = False
_original_candidates_policy_ids = None
_original_probe = None
_original_install_icmp = None


def _ids(tunnel_id: int) -> tuple[int, int, int]:
    offset = int(tunnel_id) % SPOOF_POLICY_SPAN
    table = SPOOF_TABLE_BASE + offset
    priority = SPOOF_RULE_BASE + offset
    legacy_priority = SPOOF_TABLE_BASE + offset
    if priority >= LINUX_MAIN_RULE_PRIORITY:
        raise RuntimeError(
            "spoof_v218_policy_priority_not_before_main:"
            f"priority={priority}:main={LINUX_MAIN_RULE_PRIORITY}"
        )
    return table, priority, legacy_priority


def _policy_ids_v218(name: str, tunnel_id: int) -> tuple[int, int]:
    value = str(name or "").strip().lower()
    if value == "spoof_wg":
        table, priority, _ = _ids(tunnel_id)
        return table, priority
    if _original_candidates_policy_ids is None:
        raise RuntimeError("spoof_v218_original_policy_ids_missing")
    return _original_candidates_policy_ids(value, tunnel_id)


async def _probe_v218(
    ci,
    ce,
    *,
    name: str,
    tunnel_id: int,
    rt: dict,
) -> dict:
    if _original_probe is None:
        raise RuntimeError("spoof_v218_original_probe_missing")

    value = str(name or "").strip().lower()
    if value != "spoof_wg":
        return await _original_probe(
            ci,
            ce,
            name=name,
            tunnel_id=int(tunnel_id),
            rt=rt,
        )

    table, priority, legacy_priority = _ids(tunnel_id)

    # Remove only the obsolete Spoof-owned RPDB rule from pre-V218 attempts.
    # The route table itself is intentionally preserved because V179 flushes
    # and repopulates the same historical table ID immediately afterwards.
    await ci.run(
        f"""
set +e
while ip rule del priority {int(legacy_priority)} 2>/dev/null; do :; done
true
""",
        check=False,
        timeout=15,
    )

    result = await _original_probe(
        ci,
        ce,
        name=name,
        tunnel_id=int(tunnel_id),
        rt=rt,
    )

    out = dict(result)
    out.update(
        {
            "policy_table": int(table),
            "policy_rule_priority": int(priority),
            "policy_rule_before_main": True,
            "legacy_policy_rule_removed": int(legacy_priority),
        }
    )
    return out


def _updated_meta(raw: str | None, tunnel_id: int) -> str:
    meta = v214._meta_dict(raw)
    table, priority, legacy_priority = _ids(tunnel_id)

    meta["generation"] = VERSION
    meta["qualification"] = "full-shared-l3-probe+reverse-icmp-v218"
    meta["spoof_policy_routing"] = {
        "version": VERSION,
        "table": int(table),
        "rule_priority": int(priority),
        "linux_main_rule_priority": LINUX_MAIN_RULE_PRIORITY,
        "rule_before_main": True,
        "legacy_rule_priority": int(legacy_priority),
        "legacy_rule_cleanup": "before-spoof-icmp-probe",
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


async def _install_icmp_v218(
    tunnel_id: int,
    db: Session,
    *,
    trigger: str,
    udp_error: str | None = None,
) -> dict:
    if _original_install_icmp is None:
        raise RuntimeError("spoof_v218_original_icmp_installer_missing")

    result = await _original_install_icmp(
        int(tunnel_id),
        db,
        trigger=trigger,
        udp_error=udp_error,
    )

    row = v214._row(db, int(tunnel_id))
    if row is None:
        raise RuntimeError("spoof_v218_transport_row_missing_after_success")

    row.config_text = _updated_meta(row.config_text, int(tunnel_id))
    db.commit()
    db.refresh(row)

    table, priority, legacy_priority = _ids(tunnel_id)
    out = dict(result)
    out.update(
        {
            "generation": VERSION,
            "qualification": "full-shared-l3-probe+reverse-icmp-v218",
            "policy_table": int(table),
            "policy_rule_priority": int(priority),
            "legacy_policy_rule_removed": int(legacy_priority),
        }
    )
    return out


def apply_spoof_policy_rule_priority_v218() -> None:
    global _applied
    global _original_candidates_policy_ids
    global _original_probe
    global _original_install_icmp

    if _applied:
        return

    _original_candidates_policy_ids = candidates.policy_ids
    _original_probe = v214.probe
    _original_install_icmp = v214._install_icmp

    # Keep callers that resolve through either public candidates.policy_ids or
    # common.policy_ids on one authoritative contract. V179 resolves the common
    # object dynamically, while uninstall_transport resolves the module global.
    candidates.policy_ids = _policy_ids_v218
    candidate_common.policy_ids = _policy_ids_v218

    # Scope legacy-rule cleanup and metadata to the Spoof ICMP qualification
    # path only. The shared V179 probe implementation remains unchanged.
    v214.probe = _probe_v218
    v214._install_icmp = _install_icmp_v218

    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        f"table_base={SPOOF_TABLE_BASE} "
        f"rule_base={SPOOF_RULE_BASE} "
        f"main_priority={LINUX_MAIN_RULE_PRIORITY} "
        "legacy_330xx=cleanup-before-probe "
        "tp27=unchanged vxlan=unchanged shared_probe=v179-unchanged",
        flush=True,
    )
