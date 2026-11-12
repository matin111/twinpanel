#!/usr/bin/env python3
"""Read-only protocol-by-protocol ledger integrity report.

No SSH, device state changes, quota writes, resets, or user identifiers.
A zero-byte sample is never evidence that an active protocol used no traffic.
All 16 canonical source protocols are reported, even without recent events.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND=Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0,str(BACKEND))

from sqlalchemy import text
from app.database import SessionLocal
from app.protocol_account_registry import ALL_PROTOCOL_KEYS
from app.services.quota_node_sync import _PROTOCOL_TO_QUOTA


def reliability_label(*, source_protocol: str, active_devices: int,
                      event_count: int, positive_event_count: int,
                      invalid_event_count: int) -> str:
    """Classification of the available EVIDENCE, never a fabricated byte rate."""
    if source_protocol == "shadowtls":
        # Shared inner authentication cannot assign bytes to a subscriber.
        return "per_user_attribution_unavailable"
    if invalid_event_count:
        return "invalid_counter_events_need_review"
    if not active_devices:
        return "no_active_quota_devices"
    if not event_count:
        return "no_recent_ledger_evidence"
    if not positive_event_count:
        return "only_zero_byte_events_verify_at_source"
    return "positive_attributed_ledger_evidence"


def build_report(sources: dict[str, dict], events: dict[str, dict],
                 devices: dict[str, int], sessions: dict[str, dict] | None = None) -> dict:
    sessions = sessions or {}
    items=[]
    for source in sorted(ALL_PROTOCOL_KEYS):
        canonical=_PROTOCOL_TO_QUOTA.get(source)
        if canonical is None:
            raise RuntimeError(f"METERING_PROTOCOL_MAPPING_MISSING:{source}")
        row=events.get(canonical,{})
        count=int(row.get("event_count") or 0)
        positive=int(row.get("positive_count") or 0)
        invalid=int(row.get("invalid_count") or 0)
        bytes_accepted=int(row.get("accepted_bytes") or 0)
        bytes_billable=int(row.get("billable_bytes") or 0)
        source_sessions=sessions.get(canonical,{})
        if min(count,positive,invalid,bytes_accepted,bytes_billable)<0:
            raise RuntimeError("METERING_LEDGER_NEGATIVE_AGGREGATE")
        items.append({
            "protocol":source,
            "ledger_protocol":canonical,
            "active_credentials":int(sources.get(source,{}).get("active_credentials") or 0),
            "active_quota_devices":int(devices.get(source,0)),
            "recent_events":count,
            "recent_positive_events":positive,
            # Audit-only evidence: zero-byte ledger records are not proof of
            # zero actual traffic. Keep accepted and billable totals separate.
            "recent_zero_byte_events":int(row.get("zero_count") or 0),
            "last_positive_event_utc":str(row.get("last_positive_event") or "") or None,
            "recent_authenticated_session_rows":int(source_sessions.get("recent") or 0),
            "stale_open_session_rows":int(source_sessions.get("stale") or 0),
            "recent_invalid_counter_events":invalid,
            "recent_accepted_bytes":bytes_accepted,
            "recent_billable_bytes":bytes_billable,
            "last_event_utc":str(row.get("last_event") or "") or None,
            "reliability":reliability_label(
                source_protocol=source,
                active_devices=int(devices.get(source,0)),
                event_count=count,
                positive_event_count=positive,
                invalid_event_count=invalid),
        })
    return {
        "audit":"twinpanel_accounting_integrity_v1",
        "window_hours":24,
        "protocol_count":len(items),
        "protocols":items,
        "notes":[
            "Accepted and billable bytes are ledger evidence, not traffic estimates.",
            "Do not reconcile historic usage against a subscription balance after reset or renewal.",
            "Unattributable shared ShadowTLS traffic must not be assigned to a subscriber.",
            "Zero-only events may mean no real traffic OR failed node-side metering.",
            "An active ledger session without a recent authenticated heartbeat is stale, not confirmed online.",
        ],
    }


def collect() -> dict:
    # Read-only aggregation. No ORM entities with decrypted credentials.
    with SessionLocal() as db:
        credentials={
            str(row["protocol"]):{"active_credentials":int(row["count"])}
            for row in db.execute(text("""
                SELECT protocol,COUNT(*) AS count
                FROM protocol_credentials WHERE is_active=true
                GROUP BY protocol
            """)).mappings()
        }
        devices={
            str(row["protocol"]):int(row["count"])
            for row in db.execute(text("""
                SELECT protocol,COUNT(*) AS count
                FROM quota_devices WHERE status='active'
                GROUP BY protocol
            """)).mappings()
        }
        events={
            str(row["protocol"]):dict(row)
            for row in db.execute(text("""
                SELECT protocol,COUNT(*) AS event_count,
                       COUNT(*) FILTER (WHERE accepted_bytes > 0) AS positive_count,
                       COUNT(*) FILTER (WHERE accepted_bytes < 0
                                            OR billable_bytes < 0
                                            OR uplink_delta < 0
                                            OR downlink_delta < 0) AS invalid_count,
                       COALESCE(SUM(accepted_bytes),0) AS accepted_bytes,
                       COALESCE(SUM(billable_bytes),0) AS billable_bytes,
                       MAX(created_at) AS last_event,
                       MAX(created_at) FILTER (WHERE accepted_bytes > 0) AS last_positive_event,
                       COUNT(*) FILTER (WHERE accepted_bytes = 0) AS zero_count
                FROM quota_usage_events
                WHERE created_at >= (NOW() AT TIME ZONE 'UTC') - interval '24 hours'
                GROUP BY protocol
            """)).mappings()
        }
        sessions={
            str(row["protocol"]):{
                "recent":int(row["recent"] or 0),
                "stale":int(row["stale"] or 0),
            }
            for row in db.execute(text("""
                SELECT protocol,
                       COUNT(*) FILTER (
                           WHERE last_seen_at >=
                             (NOW() AT TIME ZONE 'UTC') - interval '180 seconds'
                       ) AS recent,
                       COUNT(*) FILTER (
                           WHERE last_seen_at <
                             (NOW() AT TIME ZONE 'UTC') - interval '180 seconds'
                       ) AS stale
                FROM quota_sessions
                WHERE status='active'
                GROUP BY protocol
            """)).mappings()
        }
        db.rollback()
    return build_report(credentials,events,devices,sessions)


if __name__=="__main__":
    print(json.dumps(collect(),ensure_ascii=False,default=str))
