from __future__ import annotations

import json
import re
import time
from datetime import timezone

from sqlalchemy.orm import Session

from . import spoof_underlay_guard_v206 as guard
from .models import TunnelTransport
from .transport_candidates import spoof_wg


# ============================================================
# TWINPANEL SPOOF LAST-ERROR RECOVERY V212 + HISTORICAL TTL FIX V213
#
# V211 prevents a valid structured underlay guard from being overwritten by
# later health probes. Production rows that were already corrupted before V211
# can still have both guard metadata and the SmartAuto underlay reason missing,
# while the original decisive V206 diagnostic survives in last_error.
#
# V212 recovered only that exact historical failure shape, but anchored a fresh
# 24h quarantine to the recovery time. That made old evidence look like a new
# outage and could block both Health and explicit install before SSH even when
# the provider path had already changed.
#
# V213 keeps the strict V212 forensic signature but anchors quarantine lifetime
# to TunnelTransport.updated_at, which is the persisted observation timestamp
# written by mark() when the original failure was stored. Existing synthetic
# V212 guards are normalized in place. Expired historical evidence is preserved
# as non-blocking metadata so the current underlay can be re-qualified.
#
# Recovery/normalization is DB metadata only. It does not open SSH, inspect
# systemd, install, repair, alter framing/ports/payloads, or touch TP27/VXLAN.
# ============================================================

MARKER = "TWINPANEL_SPOOF_LAST_ERROR_RECOVERY_V213"
LEGACY_METADATA_SOURCE = "legacy_last_error_recovery_v212"
METADATA_SOURCE = "legacy_last_error_recovery_v213"
VERSION = 213

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


def _updated_at_epoch(row: TunnelTransport, *, fallback_epoch: float) -> float:
    """Return persisted row.updated_at as UTC epoch, or fail closed to fallback."""

    value = getattr(row, "updated_at", None)
    if value is None:
        return float(fallback_epoch)
    try:
        if getattr(value, "tzinfo", None) is None:
            value = value.replace(tzinfo=timezone.utc)
        epoch = float(value.timestamp())
    except Exception:
        return float(fallback_epoch)

    # A materially future timestamp is not trustworthy for quarantine ageing.
    if epoch <= 0.0 or epoch > float(fallback_epoch) + 300.0:
        return float(fallback_epoch)
    return epoch


def _historical_window(
    row: TunnelTransport,
    *,
    now_epoch: float,
) -> tuple[float, float, int, bool]:
    observed = _updated_at_epoch(row, fallback_epoch=now_epoch)
    until = observed + float(guard.UNDERLAY_QUARANTINE_SECONDS)
    age = max(0, int(now_epoch - observed))
    return observed, until, age, until > now_epoch


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


def _active_payload(
    *,
    quarantine_until: float,
    now: float,
    metadata_source: str,
) -> dict:
    return {
        "blocked": True,
        "transport": spoof_wg.NAME,
        "reason": guard.UNDERLAY_REASON,
        "quarantine_until_epoch": quarantine_until,
        "retry_after_seconds": max(0, int(quarantine_until - now)),
        "authority_unchanged": True,
        "action": "fail_fast_before_node_mutation",
        "version": VERSION,
        "metadata_source": metadata_source,
        "repair_guard_metadata": False,
    }


def _persist_last_error_recovery(
    db: Session,
    row: TunnelTransport,
    *,
    evidence: dict,
    now_epoch: float | None = None,
) -> dict | None:
    """Rehydrate historical authority without restarting the historical TTL."""

    now = time.time() if now_epoch is None else float(now_epoch)
    cfg = _meta_dict(row.config_text)

    # Never overwrite a guard that appeared between detection and persistence.
    existing = cfg.get("spoof_underlay_guard_v206")
    if isinstance(existing, dict) and existing:
        active = guard.active_underlay_quarantine(row, now_epoch=now)
        return active or None

    observed, quarantine_until, age, blocked = _historical_window(
        row,
        now_epoch=now,
    )

    smart = cfg.get("smart_auto_v21")
    if not isinstance(smart, dict):
        smart = {}
    else:
        smart = dict(smart)

    old_reason = str(smart.get("quarantine_reason") or "").strip()
    if blocked:
        smart.update(
            {
                "last_probe_ok": False,
                "quarantine_reason": guard.UNDERLAY_REASON,
                "quarantine_until_epoch": quarantine_until,
                "stable_seconds": 0.0,
                "stable_since_epoch": observed,
            }
        )

    smart.update(
        {
            "v213_recovered_at_epoch": now,
            "v213_failure_observed_at_epoch": observed,
            "v213_historical_evidence_age_seconds": age,
            "v213_historical_quarantine_active": blocked,
        }
    )
    cfg["smart_auto_v21"] = smart
    cfg["spoof_underlay_guard_v206"] = {
        "version": VERSION,
        "blocked": blocked,
        "reason": guard.UNDERLAY_REASON,
        "detected_at_epoch": observed,
        "quarantine_seconds": guard.UNDERLAY_QUARANTINE_SECONDS,
        "evidence": {
            **evidence,
            "recovered_from": "last_error",
            "historical_v206_diagnostic_signature": True,
            "original_v206_guard_metadata_was_missing": True,
            "smart_auto_reason_before_recovery": old_reason or None,
            "failure_observed_at_epoch": observed,
            "historical_evidence_age_seconds": age,
        },
        "action": (
            "fail_closed_keep_existing_authority"
            if blocked
            else "historical_evidence_preserved_requalification_allowed"
        ),
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
        raise RuntimeError("v213_last_error_mutated")
    if row.status != original_status:
        raise RuntimeError("v213_status_mutated")
    if row.enabled != original_enabled:
        raise RuntimeError("v213_enabled_mutated")

    if not blocked:
        return None
    return _active_payload(
        quarantine_until=quarantine_until,
        now=now,
        metadata_source=METADATA_SOURCE,
    )


def _normalize_existing_v212_recovery(
    db: Session,
    row: TunnelTransport | None,
    *,
    now_epoch: float,
) -> tuple[bool, dict | None]:
    """Normalize synthetic V212 recovery guards to the original failure clock."""

    if row is None:
        return False, None

    cfg = _meta_dict(row.config_text)
    current = cfg.get("spoof_underlay_guard_v206")
    if not isinstance(current, dict):
        return False, None
    if int(current.get("version") or 0) != 212:
        return False, None
    if str(current.get("metadata_source") or "") != LEGACY_METADATA_SOURCE:
        return False, None

    evidence = current.get("evidence")
    if not isinstance(evidence, dict):
        return False, None
    if str(evidence.get("recovered_from") or "") != "last_error":
        return False, None

    observed, quarantine_until, age, blocked = _historical_window(
        row,
        now_epoch=now_epoch,
    )

    smart = cfg.get("smart_auto_v21")
    if not isinstance(smart, dict):
        smart = {}
    else:
        smart = dict(smart)

    prior_reason = str(
        evidence.get("smart_auto_reason_before_recovery") or ""
    ).strip()

    if blocked:
        smart.update(
            {
                "last_probe_ok": False,
                "quarantine_reason": guard.UNDERLAY_REASON,
                "quarantine_until_epoch": quarantine_until,
                "stable_seconds": 0.0,
                "stable_since_epoch": observed,
            }
        )
    else:
        # Remove only the synthetic V212 underlay block. Do not invent a live
        # healthy result; the next normal Health/Install call must re-qualify it.
        if str(smart.get("quarantine_reason") or "").strip() == guard.UNDERLAY_REASON:
            smart["quarantine_reason"] = prior_reason or ""
            smart["quarantine_until_epoch"] = 0.0

    smart.update(
        {
            "v213_normalized_at_epoch": now_epoch,
            "v213_failure_observed_at_epoch": observed,
            "v213_historical_evidence_age_seconds": age,
            "v213_historical_quarantine_active": blocked,
        }
    )

    updated_evidence = dict(evidence)
    updated_evidence.update(
        {
            "failure_observed_at_epoch": observed,
            "historical_evidence_age_seconds": age,
            "normalized_from_v212_fresh_ttl": True,
        }
    )

    cfg["smart_auto_v21"] = smart
    cfg["spoof_underlay_guard_v206"] = {
        **current,
        "version": VERSION,
        "blocked": blocked,
        "detected_at_epoch": observed,
        "quarantine_seconds": guard.UNDERLAY_QUARANTINE_SECONDS,
        "evidence": updated_evidence,
        "action": (
            "fail_closed_keep_existing_authority"
            if blocked
            else "historical_evidence_preserved_requalification_allowed"
        ),
        "metadata_source": METADATA_SOURCE,
        "v213_normalized_at_epoch": now_epoch,
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

    if row.last_error != original_error:
        raise RuntimeError("v213_normalize_last_error_mutated")
    if row.status != original_status:
        raise RuntimeError("v213_normalize_status_mutated")
    if row.enabled != original_enabled:
        raise RuntimeError("v213_normalize_enabled_mutated")

    if not blocked:
        return True, None
    return True, _active_payload(
        quarantine_until=quarantine_until,
        now=now_epoch,
        metadata_source=METADATA_SOURCE,
    )


def _active_underlay_quarantine_for_tunnel_v212(
    db: Session,
    tunnel_id: int,
    *,
    now_epoch: float | None = None,
) -> dict | None:
    """Use current V206-V211 authority, with V213 historical-TTL normalization."""

    if _original_active_for_tunnel is None:
        raise RuntimeError("spoof_v213_original_guard_missing")

    now = time.time() if now_epoch is None else float(now_epoch)
    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == spoof_wg.NAME,
        )
        .first()
    )

    # rc.328 may already have persisted a synthetic V212 guard. Normalize it
    # before V211 sees it as authoritative, otherwise the fresh recovery clock
    # would continue to block current re-qualification.
    handled, normalized = _normalize_existing_v212_recovery(
        db,
        row,
        now_epoch=now,
    )
    if handled:
        return normalized

    active = _original_active_for_tunnel(
        db,
        int(tunnel_id),
        now_epoch=now,
    )
    if active is not None:
        return active

    evidence = _legacy_last_error_evidence(row)
    if evidence is None or row is None:
        return None

    return _persist_last_error_recovery(
        db,
        row,
        evidence=evidence,
        now_epoch=now,
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
        "legacy_signature=exact_last_error_only "
        "historical_ttl=transport_updated_at "
        "existing_v212=normalized "
        "expired_evidence=requalification_allowed "
        "repair=db_metadata_only last_error=preserved "
        "tp27=unchanged vxlan=unchanged",
        flush=True,
    )
