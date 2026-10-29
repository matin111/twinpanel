from __future__ import annotations

import ast
import json
import re
import time

from sqlalchemy.orm import Session

from . import transport_candidates as candidates
from .models import TunnelTransport
from .transport_candidates import spoof_wg
from .transport_candidates.common import mark


# ============================================================
# TWINPANEL SPOOF UNDERLAY GUARD V206 + QUARANTINE FAILFAST V207
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
# node runtime. This prevents the same known-incompatible dataplane attempt from
# repeatedly restarting services while TP27/VXLAN are already healthy.
#
# This layer does NOT alter framing, ports, payloads, TP27 or VXLAN.
# ============================================================

MARKER = "TWINPANEL_SPOOF_UNDERLAY_GUARD_V206"
FAILFAST_MARKER = "TWINPANEL_SPOOF_QUARANTINE_FAILFAST_V207"
UNDERLAY_REASON = "underlay_incompatible:reverse_carrier_not_reaching_iran"
UNDERLAY_QUARANTINE_SECONDS = 24 * 60 * 60

_EXIT_SECTION_RE = re.compile(r"\|\s*exit=(.*?)(?:\|\s*reverse_ingress=|$)", re.DOTALL)
_REVERSE_BYTES_RE = re.compile(r"shutting down \(up=\d+ down=([1-9]\d*)\)")
_ZERO_INGRESS_RE = re.compile(r"reverse_ingress=.*?counter packets 0 bytes 0", re.DOTALL)

_applied = False
_original_install = None


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
    """Return the active V206 block without mutating DB or node runtime."""

    if row is None or str(row.transport or "").strip().lower() != spoof_wg.NAME:
        return None

    cfg = _meta_dict(row.config_text)
    smart = cfg.get("smart_auto_v21")
    guard = cfg.get("spoof_underlay_guard_v206")
    if not isinstance(smart, dict) or not isinstance(guard, dict):
        return None

    reason = str(smart.get("quarantine_reason") or "").strip()
    if reason != UNDERLAY_REASON:
        return None
    if guard.get("blocked") is not True or str(guard.get("reason") or "") != reason:
        return None

    try:
        until = float(smart.get("quarantine_until_epoch") or 0.0)
    except (TypeError, ValueError):
        return None

    now = time.time() if now_epoch is None else float(now_epoch)
    remaining = max(0, int(until - now))
    if remaining <= 0:
        return None

    return {
        "blocked": True,
        "transport": spoof_wg.NAME,
        "reason": reason,
        "quarantine_until_epoch": until,
        "retry_after_seconds": remaining,
        "authority_unchanged": True,
        "action": "fail_fast_before_node_mutation",
        "version": 207,
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
        raise RuntimeError(
            "spoof_underlay_quarantined:"
            f"{active_block['reason']}:"
            f"retry_after_seconds={active_block['retry_after_seconds']}:"
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


def apply_spoof_underlay_guard_v206() -> None:
    global _applied, _original_install
    if _applied:
        return

    installer = candidates.INSTALLERS.get(spoof_wg.NAME)
    if installer is None:
        raise RuntimeError("spoof_underlay_guard_installer_missing")

    _original_install = installer
    candidates.INSTALLERS[spoof_wg.NAME] = _guarded_spoof_install
    spoof_wg.install = _guarded_spoof_install
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
