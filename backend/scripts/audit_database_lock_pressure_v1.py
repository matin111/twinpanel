"""Read-only PostgreSQL transaction/lock pressure summary for TwinPanel.

Usage (on the panel mother, using existing env):
    cd /opt/twinpanel/current/backend
    PYTHONPATH=. /opt/twinpanel/venv/bin/python scripts/audit_database_lock_pressure_v1.py

Never prints SQL statements, customer identifiers, database connection URLs or
credentials. Only groups by controlled libpq application_name / state and
reports the longest transaction age for each group. Does not end sessions.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text

from app.database import engine


ACTIVITY_SQL = """
SELECT
    CASE
      WHEN application_name IN ('twinpanel-http', 'twinpanel-worker')
        THEN application_name
      ELSE 'unattributed'
    END AS application_group,
    coalesce(state, 'unknown') AS state,
    coalesce(wait_event_type, 'none') AS wait_type,
    count(*)::integer AS sessions,
    coalesce(max(extract(epoch FROM clock_timestamp() - xact_start))
      FILTER (WHERE xact_start IS NOT NULL), 0)::integer AS oldest_txn_seconds
FROM pg_stat_activity
WHERE datname = current_database()
  AND backend_type = 'client backend'
  AND pid <> pg_backend_pid()
GROUP BY 1, 2, 3
ORDER BY sessions DESC, application_group
"""

BLOCKERS_SQL = """
SELECT
    CASE
      WHEN waiter.application_name IN ('twinpanel-http', 'twinpanel-worker')
        THEN waiter.application_name
      ELSE 'unattributed'
    END AS waiting_group,
    CASE
      WHEN holder.application_name IN ('twinpanel-http', 'twinpanel-worker')
        THEN holder.application_name
      ELSE 'unattributed'
    END AS blocking_group,
    count(*)::integer AS waiting_sessions,
    coalesce(max(extract(epoch FROM clock_timestamp() - waiter.query_start)),
      0)::integer AS max_wait_seconds
FROM pg_stat_activity AS waiter
JOIN LATERAL unnest(pg_blocking_pids(waiter.pid)) AS blocked(pid) ON true
JOIN pg_stat_activity AS holder ON holder.pid = blocked.pid
WHERE waiter.datname = current_database()
GROUP BY 1, 2
ORDER BY waiting_sessions DESC, waiting_group
"""


def _safe_rows(rows: list[Mapping[str, Any]], keys: tuple[str, ...]) -> list[dict]:
    """Produce an allowlisted aggregate only; SQL and secrets are never output."""
    return [
        {key: row[key] for key in keys}
        for row in rows
    ]


def collect() -> dict:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("DATABASE_LOCK_AUDIT_REQUIRES_POSTGRESQL")
    with engine.connect() as connection:
        # Read only even if the script is refactored later.
        connection.execute(text("SET TRANSACTION READ ONLY"))
        activity = [
            dict(row) for row in connection.execute(text(ACTIVITY_SQL)).mappings()
        ]
        blocking = [
            dict(row) for row in connection.execute(text(BLOCKERS_SQL)).mappings()
        ]
        connection.rollback()
    return {
        "read_only": True,
        "session_groups": _safe_rows(
            activity,
            ("application_group", "state", "wait_type",
             "sessions", "oldest_txn_seconds"),
        ),
        "blocker_groups": _safe_rows(
            blocking,
            ("waiting_group", "blocking_group",
             "waiting_sessions", "max_wait_seconds"),
        ),
    }


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False, separators=(",", ":")))
