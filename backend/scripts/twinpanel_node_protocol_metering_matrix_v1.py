#!/usr/bin/env python3
"""Read-only node/protocol metering evidence matrix.

Never label a protocol 'healthy' from a panel ONLINE flag, zero-byte
events, or a TCP socket. Positive accepted ledger bytes prove only that
attributed accounting happened recently, not end-to-end connectivity.
No customer identities are included; no settings or balances are changed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import text
from app.database import SessionLocal
from app.protocol_account_registry import ALL_PROTOCOL_KEYS, canonical_protocol


def classify_row(*, source: str, online_flag: str, fresh_probe: bool,
                 positive_events: int, accepted_bytes: int,
                 device_mismatch_events: int) -> str:
    if device_mismatch_events:
        return "identity_mismatch_in_ledger"
    if source == "shadowtls" and not positive_events:
        return "shadowtls_source_attribution_unverified"
    if positive_events and accepted_bytes > 0:
        return "positive_attributed_ledger_evidence"
    if not fresh_probe:
        return "node_service_probe_stale_or_missing"
    if online_flag.lower() != "online":
        return "node_service_not_online"
    return "online_without_positive_metering_evidence"


def build_matrix(configs: list[dict], aggregates: dict[tuple[int, str], dict]) -> dict:
    rows = []
    for row in configs:
        raw = str(row["protocol"]).lower()
        try:
            source = canonical_protocol(raw)
        except ValueError:
            continue
        key = (int(row["node_id"]), source)
        stats = aggregates.get(key, {})
        positive = int(stats.get("positive_events") or 0)
        accepted = int(stats.get("accepted_bytes") or 0)
        mismatches = int(stats.get("device_mismatch_events") or 0)
        fresh = bool(row.get("probe_fresh"))
        status = classify_row(
            source=source, online_flag=str(row.get("status") or ""),
            fresh_probe=fresh, positive_events=positive,
            accepted_bytes=accepted, device_mismatch_events=mismatches,
        )
        rows.append({
            "node_id": key[0], "protocol": source, "metering_evidence": status,
            "reported_service_status": str(row.get("status") or ""),
            "probe_fresh": fresh, "recent_positive_events": positive,
            "recent_accepted_bytes": accepted, "device_mismatch_events": mismatches,
        })
    rows.sort(key=lambda r: (r["node_id"], r["protocol"]))
    return {
        "audit": "twinpanel_node_protocol_metering_matrix_v1",
        "registered_protocol_count": len(ALL_PROTOCOL_KEYS),
        "configured_pairs": len(rows),
        "pairs": rows,
        "warning": "Positive ledger evidence does not prove current client connectivity or physical revocation.",
    }


def collect() -> dict:
    with SessionLocal() as db:
        configs = [dict(row) for row in db.execute(text("""
            SELECT npc.node_id, npc.protocol, npc.status,
                   (npc.checked_at IS NOT NULL AND npc.checked_at >=
                     (NOW() AT TIME ZONE 'UTC') - interval '5 minutes') AS probe_fresh
            FROM node_protocol_configs npc
            JOIN nodes n ON n.id=npc.node_id
            WHERE n.retired_at IS NULL
        """)).mappings()]
        raw_events = [dict(row) for row in db.execute(text("""
            SELECT e.node_id, e.protocol,
                   COUNT(*) FILTER (WHERE e.accepted_bytes > 0) AS positive_events,
                   COALESCE(SUM(e.accepted_bytes),0) AS accepted_bytes,
                   COUNT(*) FILTER (WHERE
                       NOT (e.protocol=d.protocol
                         OR (e.protocol='openconnect' AND d.protocol='cisco')
                         OR (e.protocol='xray' AND d.protocol='v2ray')
                         OR (e.protocol='naive' AND d.protocol='naiveproxy')
                         OR (e.protocol='naiveproxy' AND d.protocol='naive')
                       )
                   ) AS device_mismatch_events
            FROM quota_usage_events e
            JOIN quota_devices d ON d.id=e.device_id
            WHERE e.created_at >= (NOW() AT TIME ZONE 'UTC') - interval '24 hours'
            GROUP BY e.node_id,e.protocol
        """)).mappings()]
        db.rollback()
    aggregates: dict[tuple[int, str], dict] = {}
    for event in raw_events:
        try:
            protocol = canonical_protocol(str(event["protocol"]))
        except ValueError:
            continue
        key = (int(event["node_id"]), protocol)
        acc = aggregates.setdefault(key, {
            "positive_events": 0, "accepted_bytes": 0, "device_mismatch_events": 0,
        })
        for field in acc:
            acc[field] += int(event.get(field) or 0)
    return build_matrix(configs, aggregates)


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False))
