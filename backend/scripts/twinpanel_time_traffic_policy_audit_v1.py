#!/usr/bin/env python3
"""Read-only time versus traffic validity audit; never changes entitlements.

This script prints only aggregate counts, not subscriber IDs, credentials,
emails, usernames or raw connection records. Unknown legacy duration is not
an entitlement decision, and this tool never assigns an expiry or revokes.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from app.database import SessionLocal
from app.subscription_override_models import classify_time_policy


def classify_row(row) -> tuple[str, str, str]:
    sub = SimpleNamespace(
        expires_at=row["expires_at"],
        starts_at=row["starts_at"],
        activation_duration_days=row["activation_duration_days"],
    )
    plan = (
        SimpleNamespace(duration_days=row["plan_duration_days"])
        if row["plan_id"] is not None and row["plan_duration_days"] is not None
        else None
    )
    override = (
        SimpleNamespace(duration_unlimited=bool(row["duration_unlimited"]))
        if row["override_present"] else None
    )
    time_state = classify_time_policy(sub, plan, override)
    limit = max(0, int(row["traffic_limit_bytes"] or 0))
    used = max(0, int(row["traffic_used_bytes"] or 0))
    traffic_state = (
        "unlimited_volume" if limit == 0
        else "volume_exhausted" if used >= limit
        else "limited_volume"
    )
    return str(row["status"]), time_state, traffic_state


def build_summary(rows: list[dict]) -> dict:
    groups = Counter(classify_row(row) for row in rows)
    return {
        "version": "time_traffic_policy_evidence_v1",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "subscriptions_examined": len(rows),
        "by_status_time_and_volume": [
            {
                "status": status,
                "time_policy": time_policy,
                "volume_policy": volume_policy,
                "count": count,
            }
            for (status,time_policy,volume_policy),count
            in sorted(groups.items())
        ],
        "unknown_legacy_active": sum(
            count for (status,time_policy,_),count in groups.items()
            if status == "ACTIVE" and time_policy == "legacy_unknown_duration"
        ),
        "unknown_legacy_started": sum(
            1 for row in rows if str(row["status"]) == "ACTIVE"
            and classify_row(row)[1] == "legacy_unknown_duration"
            and row["starts_at"] is not None
        ),
        "conflicting_explicit_unlimited_with_expiry": sum(
            1 for row in rows if bool(row["duration_unlimited"])
            and row["expires_at"] is not None
        ),
        "explicit_unlimited_active": sum(
            count for (status,time_policy,_),count in groups.items()
            if status == "ACTIVE" and time_policy == "explicit_unlimited"
        ),
        "limitations": (
            "Historical legacy unknown accounts require provenance review; "
            "this report neither grants unlimited duration nor changes "
            "established connections, balances, expiry or first-use dates."
        ),
    }


def audit() -> dict:
    with SessionLocal() as db:
        try:
            db.execute(text("SET TRANSACTION READ ONLY"))
            db.execute(text("SET LOCAL statement_timeout = '5000ms'"))
            rows = [dict(row) for row in db.execute(text("""
                SELECT CAST(s.status AS text) AS status,
                       s.starts_at, s.expires_at,
                       s.activation_duration_days, s.plan_id,
                       p.duration_days AS plan_duration_days,
                       o.subscription_id IS NOT NULL AS override_present,
                       COALESCE(o.duration_unlimited,FALSE) AS duration_unlimited,
                       s.traffic_limit_bytes, s.traffic_used_bytes
                  FROM subscriptions s
                  LEFT JOIN plans p ON p.id=s.plan_id
                  LEFT JOIN subscription_runtime_overrides o
                    ON o.subscription_id=s.id
            """)).mappings()]
            return build_summary(rows)
        finally:
            db.rollback()


if __name__ == "__main__":
    print(json.dumps(audit(),ensure_ascii=False,indent=2))
