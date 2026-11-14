"""Read-only, share-token scoped per-session usage; never infer from account totals."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Node
from ..quota_models import QuotaSession, QuotaUsageEvent
from .account_delivery import _subscription_from_share_token

router = APIRouter(prefix="/v1/connect", tags=["connection-session-history"])

def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

@router.get("/{token}/sessions")
def connection_session_history(token: str, db: Session = Depends(get_db)):
    """Only show real sessions, with bytes attributed to their exact session_key and node.

    Collector events without a session key are intentionally NOT assigned to a
    session. Their bytes remain accounted in the main subscription quota.
    """
    subscription = _subscription_from_share_token(token, db)
    sessions = (
        db.query(QuotaSession)
        .filter(QuotaSession.subscription_id == subscription.id)
        .order_by(QuotaSession.started_at.desc(), QuotaSession.id.desc())
        .limit(50)
        .all()
    )
    if not sessions:
        return {"items": [], "limit": 50, "attribution": "session_key_only"}
    nodes = {n.id: n for n in db.query(Node).filter(
        Node.id.in_({row.node_id for row in sessions})
    ).all()}
    # Query bounded by the latest 50 rows; no N+1 across hundreds of events.
    keys = {(s.node_id, s.session_key) for s in sessions}
    oldest_start = min(s.started_at for s in sessions) - timedelta(seconds=10)
    rows = (
        db.query(
            QuotaUsageEvent.node_id,
            QuotaUsageEvent.session_key,
            QuotaUsageEvent.reported_at,
            QuotaUsageEvent.uplink_delta,
            QuotaUsageEvent.downlink_delta,
            QuotaUsageEvent.billable_bytes,
        )
        .filter(
            QuotaUsageEvent.subscription_id == subscription.id,
            QuotaUsageEvent.reported_at >= oldest_start,
            QuotaUsageEvent.session_key.isnot(None),
            QuotaUsageEvent.node_id.in_({k[0] for k in keys}),
            QuotaUsageEvent.session_key.in_({k[1] for k in keys}),
        )
        .all()
    )
    grouped: dict[tuple[int, str], list] = {}
    for row in rows:
        grouped.setdefault((row.node_id, row.session_key), []).append(row)
    items = []
    now = datetime.utcnow()
    for s in sessions:
        ended = s.ended_at or (s.last_seen_at if s.status != "active" else None)
        event_rows = [
            event for event in grouped.get((s.node_id, s.session_key), [])
            if event.reported_at >= s.started_at - timedelta(seconds=10)
            and (ended is None or event.reported_at <= ended + timedelta(minutes=5))
        ]
        # Directional counters are raw measured deltas; do not substitute
        # accepted_bytes as that includes quota enforcement rather than wire use.
        up = sum(max(0, int(event.uplink_delta or 0)) for event in event_rows)
        down = sum(max(0, int(event.downlink_delta or 0)) for event in event_rows)
        node = nodes.get(s.node_id)
        # The country of the node is available only if recorded on this node.
        country = getattr(node, "country", None) if node else None
        items.append({
            "id": s.id,
            "protocol": s.protocol,
            "node_id": s.node_id,
            "country": str(country) if country else None,
            "started_at": _iso(s.started_at),
            "ended_at": _iso(ended),
            "last_seen_at": _iso(s.last_seen_at),
            "active": s.status == "active" and ended is None,
            "duration_seconds": max(0, int(((ended or now) - s.started_at).total_seconds())),
            "upload_bytes": up if event_rows else None,
            "download_bytes": down if event_rows else None,
            "total_bytes": up + down if event_rows else None,
            "usage_measured": bool(event_rows),
        })
    return {"items": items, "limit": 50, "attribution": "session_key_only"}
