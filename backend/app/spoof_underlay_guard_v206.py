from __future__ import annotations

import ast
import json
import re
import time

from sqlalchemy.orm import Session

from . import transport_candidates as candidates
from .database import SessionLocal
from .models import TunnelTransport
from .transport_candidates import spoof_wg
from .transport_candidates.common import mark


# ============================================================
# TWINPANEL SPOOF UNDERLAY GUARD V206 + QUARANTINE FAILFAST V207/V208/V211
#
# Production Tunnel #8 proved a specific failure shape:
#   * Spoof forward carrier reaches Exit;
#   * Exit produces reverse carrier bytes;
#   * the Iran-owned reverse ingress nft counter remains at zero;
#   * TP27 Fast / Kernel VXLAN remain healthy and authoritative.
#
# V206 classifies that evidence as an underlay incompatibility, persists the
# evidence, and quarantines the failed Spoof candidate so selection stays
# fail-closed.
#
# V207 makes that quarantine operational for explicit install/repair too. While
# the exact V206 underlay quarantine is still active, a repeated Spoof install
# is rejected before the original installer opens SSH connections or mutates any
# node runtime.
#
# V208 handles production rows where a later candidate metadata rewrite kept the
# SmartAuto quarantine namespace but dropped spoof_underlay_guard_v206. The exact
# active V206 reason is recovered only for an enabled failed Spoof row whose last
# probe is explicitly failed. The guard metadata is rehydrated in DB before the
# request is rejected; no node runtime is touched.
#
# V211 closes the health/probe authority gap. A valid structured V206/V208 guard
# is authoritative even when a later generic health probe overwrote SmartAuto's
# quarantine_reason/status. Spoof health is rejected before SmartAuto cache,
# SSH, systemd inspection or candidate_probe, preserving the underlay evidence
# and avoiding any node runtime mutation. The structured guard carries its own
# expiry derived from detected_at_epoch + quarantine_seconds.
#
# This layer does NOT alter framing, ports, payloads, TP27 or VXLAN.
# ============================================================

MARKER = "TWINPANEL_SPOOF_UNDERLAY_GUARD_V206"
FAILFAST_MARKER = "TWINPANEL_SPOOF_QUARANTINE_FAILFAST_V207"
RECOVERY_MARKER = "TWINPANEL_SPOOF_QUARANTINE_RECOVERY_V208"
HEALTH_GUARD_MARKER = "TWINPANEL_SPOOF_HEALTH_GUARD_V211"
UNDERLAY_REASON = "underlay_incompatible:reverse_carrier_not_reaching_iran"
UNDERLAY_QUARANTINE_SECONDS = 24 * 60 * 60

_EXIT_SECTION_RE = re.compile(r"\|\s*exit=(.*?)(?:\|\s*reverse_ingress=|$)", re.DOTALL)
_REVERSE_BYTES_RE = re.compile(r"shutting down \(up=\d+ down=([1-9]\d*)\)")
_ZERO_INGRESS_RE = re.compile(r"reverse_ingress=.*?counter packets 0 bytes 0", re.DOTALL)

_applied = False
_original_install = None
_original_candidate_health = None


def _meta_dict(raw: str | None) -> dict:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    try:
        value = ast.literal_eval(text)
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    return {}


def _row_status(row: TunnelTransport) -> str:
    raw = getattr(row.status, "value", row.status)
    return str(raw or "").strip().lower()


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _exit_reverse_progress(message: str) -> bool:
    match = _EXIT_SECTION_RE.search(str(message or ""))
    if not match:
        return False
    return _REVERSE_BYTES_RE.search(match.group(1)) is not None


def classify_spoof_install_failure(message: str) -> str | None:
    text = str(message or "")
    if "peer_ping_failed:" not in text:
        return None
    if not _exit_reverse_progress(text):
        return None
    if _ZERO_INGRESS_RE.search(text) is None:
        return None
    return UNDERLAY_REASON


def active_underlay_quarantine(
    row: TunnelTransport | None,
    *,
    now_epoch: float | None = None,
) -> dict | None:
    """Return the active V206/V208 block without mutating DB or node runtime.

    V211 makes the structured spoof_underlay_guard_v206 namespace authoritative.
    Generic health telemetry is allowed to update SmartAuto fields, but it may
    not erase already-proven underlay incompatibility until the guard's own
    quarantine lifetime expires.
    """

    if row is None or str(row.transport or "").strip().lower() != spoof_wg.NAME:
        return None

    cfg = _meta_dict(row.config_text)
    smart = cfg.get("smart_auto_v21")
    if not isinstance(smart, dict):
        smart = {}

    guard = cfg.get("spoof_underlay_guard_v206")
    guard_valid = bool(
        isinstance(guard, dict)
        and guard.get("blocked") is True
        and str(guard.get("reason") or "").strip() == UNDERLAY_REASON
    )

    now = time.time() if now_epoch is None else float(now_epoch)

    # V211: structured evidence wins over mutable SmartAuto telemetry. Derive
    # expiry from the guard itself so a later 120s generic probe quarantine or
    # status rewrite cannot hide the original 24h underlay finding.
    if guard_valid:
        detected = _safe_float(guard.get("detected_at_epoch"), 0.0)
        duration = _safe_float(
            guard.get("quarantine_seconds"),
            float(UNDERLAY_QUARANTINE_SECONDS),
        )
        guard_until = (
            detected + max(0.0, duration)
            if detected > 0.0 and duration > 0.0
            else 0.0
        )

        smart_until = 0.0
        smart_reason = str(smart.get("quarantine_reason") or "").strip()
        if smart_reason == UNDERLAY_REASON:
            smart_until = _safe_float(smart.get("quarantine_until_epoch"), 0.0)

        until = max(guard_until, smart_until)
        remaining = max(0, int(until - now))
        if remaining <= 0:
            return None

        return {
            "blocked": True,
            "transport": spoof_wg.NAME,
            "reason": UNDERLAY_REASON,
            "quarantine_until_epoch": until,
            "retry_after_seconds": remaining,
            "authority_unchanged": True,
            "action": "fail_fast_before_node_mutation",
            "version": 211,
            "metadata_source": "v206_guard",
            "repair_guard_metadata": False,
        }

    # Backward-compatible V208 recovery path for rows where the structured
    # namespace was lost before V208 shipped. This path intentionally remains
    # strict to avoid converting unrelated generic health failures into the
    # specific V206 underlay classification.
    reason = str(smart.get("quarantine_reason") or "").strip()
    if reason != UNDERLAY_REASON:
        return None

    until = _safe_float(smart.get("quarantine_until_epoch"), 0.0)
    remaining = max(0, int(until - now))
    if remaining <= 0:
        return None

    legacy_guard_missing = not isinstance(guard, dict) or not guard
    if not legacy_guard_missing:
        return None
    if not bool(row.enabled):
        return None
    if _row_status(row) != "failed":
        return None
    if smart.get("last_probe_ok") is not False:
        return None

    return {
        "blocked": True,
        "transport": spoof_wg.NAME,
        "reason": reason,
        "quarantine_until_epoch": until,
        "retry_after_seconds": remaining,
        "authority_unchanged": True,
        "action": "fail_fast_before_node_mutation",
        "version": 208,
        "metadata_source": "smart_auto_v21_recovery_v208",
        "repair_guard_metadata": True,
    }


def active_underlay_quarantine_for_tunnel(
    db: Session,
    tunnel_id: int,
    *,
    now_epoch: float | None = None,
) -> dict | None:
    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == spoof_wg.NAME,
        )
        .first()
    )
    return active_underlay_quarantine(row, now_epoch=now_epoch)


def _restore_recovered_guard_metadata(
    db: Session,
    tunnel_id: int,
    active_block: dict,
) -> None:
    """Repair only the missing guard namespace for an already-active quarantine."""

    if active_block.get("repair_guard_metadata") is not True:
        return

    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == spoof_wg.NAME,
        )
        .first()
    )
    if row is None:
        return

    cfg = _meta_dict(row.config_text)
    smart = cfg.get("smart_auto_v21")
    if not isinstance(smart, dict):
        return
    if str(smart.get("quarantine_reason") or "").strip() != UNDERLAY_REASON:
        return

    existing = cfg.get("spoof_underlay_guard_v206")
    if isinstance(existing, dict) and existing:
        return

    now = time.time()
    detected = smart.get("last_probe_epoch") or smart.get("stable_since_epoch") or now
    cfg["spoof_underlay_guard_v206"] = {
        "version": 208,
        "blocked": True,
        "reason": UNDERLAY_REASON,
        "detected_at_epoch": detected,
        "quarantine_seconds": UNDERLAY_QUARANTINE_SECONDS,
        "evidence": {
            "recovered_from": "smart_auto_v21",
            "original_v206_guard_metadata_was_missing": True,
        },
        "action": "fail_closed_keep_existing_authority",
        "recovered_at_epoch": now,
    }
    row.config_text = json.dumps(
        cfg,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    db.commit()
    db.refresh(row)


def _persist_underlay_guard(
    db: Session,
    tunnel_id: int,
    *,
    reason: str,
    original_error: str,
) -> None:
    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == int(tunnel_id),
            TunnelTransport.transport == spoof_wg.NAME,
        )
        .first()
    )
    if row is None:
        return

    now = time.time()
    cfg = _meta_dict(row.config_text)
    smart = cfg.get("smart_auto_v21")
    if not isinstance(smart, dict):
        smart = {}
    smart.update(
        {
            "last_probe_epoch": now,
            "last_probe_ok": False,
            "quarantine_reason": reason,
            "quarantine_until_epoch": now + float(UNDERLAY_QUARANTINE_SECONDS),
            "stable_seconds": 0.0,
            "stable_since_epoch": now,
        }
    )
    cfg["smart_auto_v21"] = smart
    cfg["spoof_underlay_guard_v206"] = {
        "version": 206,
        "blocked": True,
        "reason": reason,
        "detected_at_epoch": now,
        "quarantine_seconds": UNDERLAY_QUARANTINE_SECONDS,
        "evidence": {
            "peer_ping_failed": True,
            "exit_reverse_bytes_nonzero": True,
            "iran_reverse_ingress_packets": 0,
        },
        "action": "fail_closed_keep_existing_authority",
    }

    mark(
        db,
        int(tunnel_id),
        spoof_wg.NAME,
        status="failed",
        error=f"{reason} | {original_error}",
        enabled=True,
        meta=json.dumps(cfg, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
    )


async def _guarded_spoof_install(tunnel_id: int, db: Session) -> dict:
    if _original_install is None:
        raise RuntimeError("spoof_underlay_guard_original_installer_missing")

    active_block = active_underlay_quarantine_for_tunnel(db, int(tunnel_id))
    if active_block is not None:
        _restore_recovered_guard_metadata(db, int(tunnel_id), active_block)
        raise RuntimeError(
            "spoof_underlay_quarantined:"
            f"{active_block['reason']}:"
            f"retry_after_seconds={active_block['retry_after_seconds']}:"
            f"metadata_source={active_block['metadata_source']}:"
            "authority_unchanged=true"
        )

    try:
        return await _original_install(int(tunnel_id), db)
    except RuntimeError as exc:
        message = str(exc)
        reason = classify_spoof_install_failure(message)
        if reason is not None:
            _persist_underlay_guard(
                db,
                int(tunnel_id),
                reason=reason,
                original_error=message,
            )
        raise


async def _guarded_candidate_health_remote_v211(
    tunnel_id: int,
    name: str,
    cfg: dict,
) -> tuple[str, dict]:
    """Fail closed before SmartAuto cache/SSH/probe for quarantined Spoof.

    The function intentionally performs no write, no SSH connection and no
    service inspection in the blocked path. This makes a Health Test safe while
    preserving the original underlay evidence for operator review.
    """

    if _original_candidate_health is None:
        raise RuntimeError("spoof_health_guard_original_probe_missing")

    normalized = str(name or "").strip().lower()
    if normalized != spoof_wg.NAME:
        return await _original_candidate_health(int(tunnel_id), normalized, cfg)

    db = SessionLocal()
    try:
        active_block = active_underlay_quarantine_for_tunnel(db, int(tunnel_id))
    finally:
        db.close()

    if active_block is None:
        return await _original_candidate_health(int(tunnel_id), normalized, cfg)

    error = (
        "spoof_underlay_quarantined:"
        f"{active_block['reason']}:"
        f"retry_after_seconds={active_block['retry_after_seconds']}:"
        f"metadata_source={active_block['metadata_source']}:"
        "health_probe_skipped=true:"
        "node_mutation=false:"
        "authority_unchanged=true"
    )
    return normalized, {
        "ok": False,
        "latency_ms": None,
        "packet_loss_pct": None,
        "restart_count": None,
        "stable_seconds": 0.0,
        "error": error,
        "underlay_reason": active_block["reason"],
        "quarantine_until_epoch": active_block["quarantine_until_epoch"],
        "retry_after_seconds": active_block["retry_after_seconds"],
        "guard_version": 211,
        "telemetry_source": "spoof_underlay_guard_v211",
        "probe_skipped": True,
        "node_mutation": False,
        "authority_unchanged": True,
    }


def apply_spoof_underlay_guard_v206() -> None:
    global _applied, _original_install, _original_candidate_health
    if _applied:
        return

    installer = candidates.INSTALLERS.get(spoof_wg.NAME)
    if installer is None:
        raise RuntimeError("spoof_underlay_guard_installer_missing")

    # smart_transport_auto_v21 is already imported by spoof_candidate_policy_v202
    # before this bootstrap hook runs. Importing it here avoids changing that
    # module's large health implementation while still replacing its process-wide
    # function binding used by API workers and the transport manager.
    from . import smart_transport_auto_v21 as smart

    _original_install = installer
    _original_candidate_health = smart.candidate_health_remote_v21

    candidates.INSTALLERS[spoof_wg.NAME] = _guarded_spoof_install
    spoof_wg.install = _guarded_spoof_install
    smart.candidate_health_remote_v21 = _guarded_candidate_health_remote_v211
    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        f"reason={UNDERLAY_REASON} "
        f"quarantine_seconds={UNDERLAY_QUARANTINE_SECONDS} "
        "scope=spoof_wg_only tp27=unchanged vxlan=unchanged",
        flush=True,
    )
    print(
        f"{FAILFAST_MARKER}_ACTIVE "
        "explicit_install=blocked_during_active_underlay_quarantine "
        "node_mutation=none authority=unchanged",
        flush=True,
    )
    print(
        f"{RECOVERY_MARKER}_ACTIVE "
        "legacy_missing_guard=smart_auto_exact_reason_only "
        "repair=db_metadata_only node_mutation=none",
        flush=True,
    )
    print(
        f"{HEALTH_GUARD_MARKER}_ACTIVE "
        "structured_guard=authoritative_before_smart_cache "
        "health_probe=blocked_before_ssh node_mutation=none "
        "evidence=preserved authority=unchanged",
        flush=True,
    )
