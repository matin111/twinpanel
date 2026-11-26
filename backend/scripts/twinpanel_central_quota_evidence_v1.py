#!/usr/bin/env python3
"""Read-only central quota evidence for all provisioned protocol families.

No SQL writes, API calls, node restarts, credential exports or user IDs.
Recent positive accepted bytes are evidence of metering, NOT proof that
an arbitrary user's traffic and expiry are correct. No positive event can
also mean no client used that protocol in this window.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app.database import SessionLocal
from app.protocol_account_registry import ALL_PROTOCOL_KEYS, canonical_protocol


def _canonical(value: Any) -> str | None:
    try:
        return canonical_protocol(str(value or ""))
    except (TypeError, ValueError):
        return None


def _protocol_totals(rows: list[dict], name: str) -> dict[str, dict[str, int]]:
    totals: dict[str, dict[str, int]] = {}
    for row in rows:
        protocol = _canonical(row.get("protocol"))
        if not protocol:
            continue
        values = totals.setdefault(protocol, {})
        for key, raw in row.items():
            if key != "protocol":
                values[key] = int(values.get(key, 0)) + int(raw or 0)
    return totals


def build_report(
    *,
    devices: list[dict],
    cursors: list[dict],
    positive_events: list[dict],
    cursor_device_pairs: list[dict],
    expiry_flags: dict,
    enforcement: list[dict],
    observed_at_utc: str,
) -> dict:
    device_counts = _protocol_totals(devices, "devices")
    cursor_counts = _protocol_totals(cursors, "cursors")
    accepted_counts = _protocol_totals(positive_events, "accepted")
    invalid_pairs = []
    for pair in cursor_device_pairs:
        src = _canonical(pair.get("source_protocol"))
        dev = _canonical(pair.get("device_protocol"))
        if not src or src != dev:
            invalid_pairs.append({
                "source_protocol": str(pair.get("source_protocol") or "unknown"),
                "device_protocol": str(pair.get("device_protocol") or "unknown"),
                "cursor_count": int(pair.get("cursor_count") or 0),
            })
    protocols: list[dict] = []
    for protocol in ALL_PROTOCOL_KEYS:
        provisioned = int(device_counts.get(protocol, {}).get("device_count", 0))
        cursor_total = int(cursor_counts.get(protocol, {}).get("cursor_count", 0))
        fresh_cursor = int(cursor_counts.get(protocol, {}).get("recent_cursors", 0))
        events = int(accepted_counts.get(protocol, {}).get("positive_events", 0))
        accepted = int(accepted_counts.get(protocol, {}).get("accepted_bytes", 0))
        mismatches = sum(int(row["cursor_count"]) for row in invalid_pairs
                         if _canonical(row["source_protocol"]) == protocol)
        if mismatches:
            evidence = "cursor_device_protocol_mismatch"
        elif events > 0 and accepted > 0:
            evidence = "positive_attributed_ledger_events"
        elif protocol == "shadowtls":
            evidence = "unverified_shadowtls_identity_inner"
        elif fresh_cursor:
            evidence = "fresh_counter_but_no_positive_usage"
        elif provisioned:
            evidence = "no_recent_positive_usage_observed"
        else:
            evidence = "no_provisioned_devices"
        protocols.append({
            "protocol": protocol,
            "provisioned_devices": provisioned,
            "cursor_count": cursor_total,
            "fresh_cursors_30m": fresh_cursor,
            "positive_events_6h": events,
            "accepted_bytes_6h": accepted,
            "identity_mismatch_cursors": mismatches,
            "evidence": evidence,
        })
    failed_revoke = sum(int(row.get("count") or 0) for row in enforcement
                        if row.get("command_type") == "revoke_subscription"
                        and row.get("status") == "failed")
    pending_revoke = sum(int(row.get("count") or 0) for row in enforcement
                         if row.get("command_type") == "revoke_subscription"
                         and row.get("status") in ("pending", "controller_pending", "controller_processing"))
    return {
        "version": "central_quota_evidence_v1",
        "observed_at_utc": observed_at_utc,
        "registered_protocols": len(ALL_PROTOCOL_KEYS),
        "protocols": protocols,
        "cursor_identity_mismatch_count": sum(int(x["cursor_count"]) for x in invalid_pairs),
        "cursor_identity_mismatch_pairs": invalid_pairs,
        "first_use_date_flags": {str(k): int(v or 0) for k, v in expiry_flags.items()},
        "revoke_commands_failed_24h": failed_revoke,
        "revoke_commands_pending_24h": pending_revoke,
        "enforcement": enforcement,
        "limitations": (
            "Positive ledger events prove only recent attributed accounting; "
            "no traffic can mean an idle protocol. Per-user end-to-end traffic, "
            "first connection and physical revocation require separate canary tests."
        ),
    }


def gather(db) -> dict:
    # A bounded read-only transaction: do not compete with quota writers.
    db.execute(text("SET TRANSACTION READ ONLY"))
    db.execute(text("SET LOCAL statement_timeout = '7000ms'"))
    devices = [dict(r) for r in db.execute(text("""
        SELECT protocol, count(*) AS device_count
          FROM quota_devices GROUP BY protocol
    """)).mappings()]
    cursors = [dict(r) for r in db.execute(text("""
        SELECT protocol, count(*) AS cursor_count,
               count(*) FILTER (WHERE updated_at >= NOW() - interval '30 minutes')
                   AS recent_cursors
          FROM quota_cursors GROUP BY protocol
    """)).mappings()]
    # This uses the existing partial ix_quota_usage_recent_accepted index
    # instead of scanning the 6.7-million-row events table on every audit.
    positive_events = [dict(r) for r in db.execute(text("""
        SELECT protocol, count(*) AS positive_events,
               COALESCE(sum(accepted_bytes),0) AS accepted_bytes
          FROM quota_usage_events
         WHERE accepted_bytes > 0
           AND reported_at >= NOW() - interval '6 hours'
         GROUP BY protocol
    """)).mappings()]
    pairs = [dict(r) for r in db.execute(text("""
        SELECT c.protocol AS source_protocol,
               d.protocol AS device_protocol,
               count(*) AS cursor_count
          FROM quota_cursors c JOIN quota_devices d ON d.id=c.device_id
         GROUP BY c.protocol, d.protocol
    """)).mappings()]
    dates = dict(db.execute(text("""
        SELECT
          count(*) FILTER (
            WHERE status='ACTIVE' AND starts_at IS NULL AND expires_at IS NOT NULL
          ) AS active_expiry_without_start,
          count(*) FILTER (
            WHERE status='ACTIVE' AND starts_at IS NULL AND expires_at IS NULL
          ) AS active_waiting_for_first_use,
          count(*) FILTER (
            WHERE starts_at IS NOT NULL AND expires_at < starts_at
          ) AS expiry_before_start
          FROM subscriptions
    """)).mappings().one())
    enforcement = [dict(r) for r in db.execute(text("""
        SELECT command_type,status,count(*) AS count
          FROM quota_node_commands
         WHERE issued_at >= NOW()-interval '24 hours'
           AND command_type IN ('revoke_subscription','restore_subscription')
         GROUP BY command_type,status
    """)).mappings()]
    return build_report(
        devices=devices, cursors=cursors, positive_events=positive_events,
        cursor_device_pairs=pairs, expiry_flags=dates,
        enforcement=enforcement,
        observed_at_utc=datetime.now(timezone.utc).isoformat(),
    )


if __name__ == "__main__":
    with SessionLocal() as session:
        try:
            report = gather(session)
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            session.rollback()
