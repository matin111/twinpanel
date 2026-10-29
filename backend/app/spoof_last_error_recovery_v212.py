from __future__ import annotations

import json
import re
import time

from sqlalchemy.orm import Session

from . import spoof_underlay_guard_v206 as guard
from .models import TunnelTransport
from .transport_candidates import spoof_wg


# ============================================================
# TWINPANEL SPOOF LAST-ERROR RECOVERY V212
#
# V211 prevents a valid structured underlay guard from being overwritten by
# later health probes. Production rows that were already corrupted before V211
# can still have both guard metadata and the SmartAuto underlay reason missing,
# while the original decisive V206 diagnostic survives in last_error.
#
# V212 recovers only that exact historical failure shape:
#   * enabled + failed Spoof row;
#   * peer_ping_failed diagnostic;
#   * Iran local carrier made forward progress but reverse down stayed zero;
#   * Exit reverse carrier made non-zero progress;
#   * the Tunnel-specific Iran reverse-ingress nft rule stayed at 0 packets.
#
# Recovery is DB metadata only. It does not open SSH, inspect systemd, install,
# repair, alter framing/ports/payloads, or touch TP27/VXLAN authority.
# ============================================================

MARKER = "TWINPANEL_SPOOF_LAST_ERROR_RECOVERY_V212"
METADATA_SOURCE = "legacy_last_error_recovery_v212"

_IRAN_SECTION_RE = re.compile(r"^(.*?)(?:\|\s*exit=)", re.DOTALL)
_IRAN_FORWARD_ZERO_REVERSE_RE = re.compile(
    r"shutting down \(up=([1-9]\d*) down=0\)"
)
_ZERO_INGRESS_RE = re.compile(
    r"reverse_ingress=.*?counter packets 0 bytes 0",
    re.DOTALL,
)

_applied = False
_original_active_for_tunnel = None


def _row_status(row: TunnelTransport) -> str:
    raw = getattr(row.status, "value", row.status)
    return str(raw or "").strip().lower()


def _meta_dict(raw: str | None) -> dict:
    return guard._meta_dict(raw)


def _legacy_last_error_evidence(row: TunnelTransport | None) -> dict | None:
    """Return strict historical V206 evidence from last_error, or None."""

    if row is None:
        return None
    if str(row.transport or "").strip().lower() != spoof_wg.NAME:
        return None
    if not bool(row.enabled):
        return None
    if _row_status(row) != "failed":
        return None

    cfg = _meta_dict(row.config_text)
    existing = cfg.get("spoof_underlay_guard_v206")
    if isinstance(existing, dict) and existing:
        return None

    text = str(row.last_error or "")
    if not text:
        return None

    # Reuse the original V206 classifier first. That already requires:
    # peer_ping_failed + Exit non-zero reverse bytes + zero Iran ingress.
    if guard.classify_spoof_install_failure(text) != guard.UNDERLAY_REASON:
        return None

    iran_section = _IRAN_SECTION_RE.search(text)
    if not iran_section:
        return None
    if _IRAN_FORWARD_ZERO_REVERSE_RE.search(iran_section.group(1)) is None:
        return None

    tunnel_id = int(getattr(row, "tunnel_id", 0) or 0)
    if tunnel_id <= 0:
        return None

    reverse_rule = f'TwinPanel-SPOOF-WG-{tunnel_id}-REV'
    if reverse_rule not in text:
        return None
    if _ZERO_INGRESS_RE.search(text) is None:
        return None

    return {
        "peer_ping_failed": True,
        "iran_forward_progress_reverse_zero": True,
        "exit_reverse_bytes_nonzero": True,
        "iran_reverse_ingress_packets": 0,
        "tunnel_reverse_rule": reverse_rule,
    }


def _persist_last_error_recovery(
    db: Session,
    row: TunnelTransport,
    *,
    evidence: dict,
    now_epoch: float | None = None,
) -> dict:
    """Rehydrate V206 authority from exact persisted diagnostics only."""

    now = time.time() if now_epoch is None else float(now_epoch)
    cfg = _meta_dict(row.config_text)

    # Never overwrite a guard that appeared between detection and persistence.
    existing = cfg.get("spoof_underlay_guard_v206")
    if isinstance(existing, dict) and existing:
        active = guard.active_underlay_quarantine(row, now_epoch=now)
        return active or {}

    smart = cfg.get("smart_auto_v21")
    if not isinstance(smart, dict):
        smart = {}
    else:
        smart = dict(smart)

    old_reason = str(smart.get("quarantine_reason") or "").strip()
    existing_until = guard._safe_float(
        smart.get("quarantine_until_epoch"),
        0.0,
    )
    quarantine_until = max(
        existing_until,
        now + float(guard.UNDERLAY_QUARANTINE_SECONDS),
    )

    smart.update(
        {
            "last_probe_ok": False,
            "quarantine_reason": guard.UNDERLAY_REASON,
            "quarantine_until_epoch": quarantine_until,
            "stable_seconds": 0.0,
            "stable_since_epoch": now,
            "v212_recovered_at_epoch": now,
        }
    )
    cfg["smart_auto_v21"] = smart
    cfg["spoof_underlay_guard_v206"] = {
        "version": 212,
        "blocked": True,
        "reason": guard.UNDERLAY_REASON,
        "detected_at_epoch": now,
        "quarantine_seconds": guard.UNDERLAY_QUARANTINE_SECONDS,
        "evidence": {
            **evidence,
            "recovered_from": "last_error",
            "historical_v206_diagnostic_signature": True,
            "original_v206_guard_metadata_was_missing": True,
            "smart_auto_reason_before_recovery": old_reason or None,
        },
        "action": "fail_closed_keep_existing_authority",
        "recovered_at_epoch": now,
        "metadata_source": METADATA_SOURCE,
    }

    original_error = row.last_error
    original_status = row.status
    original_enabled = row.enabled

    row.config_text = json.dumps(
        cfg,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    db.commit()
    db.refresh(row)

    # Recovery must be metadata-only; preserve candidate/operator evidence.
    if row.last_error != original_error:
        raise RuntimeError("v212_last_error_mutated")
    if row.status != original_status:
        raise RuntimeError("v212_status_mutated")
    if row.enabled != original_enabled:
        raise RuntimeError("v212_enabled_mutated")

    remaining = max(0, int(quarantine_until - now))
    return {
        "blocked": True,
        "transport": spoof_wg.NAME,
        "reason": guard.UNDERLAY_REASON,
        "quarantine_until_epoch": quarantine_until,
        "retry_after_seconds": remaining,
        "authority_unchanged": True,
        "action": "fail_fast_before_node_mutation",
        "version": 212,
        "metadata_source": METADATA_SOURCE,
        "repair_guard_metadata": False,
    }


def _active_underlay_quarantine_for_tunnel_v212(
    db: Session,
    tunnel_id: int,
    *,
    now_epoch: float | None = None,
) -> dict | None:
    """Use current V206-V211 authority, then recover exact legacy corruption."""

    if _original_active_for_tunnel is None:
        raise RuntimeError("spoof_v212_original_guard_missing")

    active = _original_active_for_tunnel(
        db,
        int(tunnel_id),
        now_epoch=now_epoch,
    )
    if active is not None:
        return active

    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == spoof_wg.NAME,
        )
        .first()
    )
    evidence = _legacy_last_error_evidence(row)
    if evidence is None or row is None:
        return None

    return _persist_last_error_recovery(
        db,
        row,
        evidence=evidence,
        now_epoch=now_epoch,
    )


def apply_spoof_last_error_recovery_v212() -> None:
    global _applied, _original_active_for_tunnel
    if _applied:
        return

    _original_active_for_tunnel = guard.active_underlay_quarantine_for_tunnel
    guard.active_underlay_quarantine_for_tunnel = (
        _active_underlay_quarantine_for_tunnel_v212
    )
    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        "legacy_corruption=exact_last_error_signature_only "
        "repair=db_metadata_only health=blocked_before_ssh "
        "install=blocked_before_node_mutation "
        "last_error=preserved tp27=unchanged vxlan=unchanged",
        flush=True,
    )
