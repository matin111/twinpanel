"""Admin-only, paginated read of recorded manual operations.

Never expose credentials, raw request bodies, tokens, or client IPs.
"""
from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..models import User
from ..quota_models import QuotaAuditLog

router = APIRouter(
    prefix="/v1/admin/activity",
    tags=["admin-activity"],
    dependencies=[Depends(require_admin)],
)

@router.get("")
def admin_activity_list(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category: str = Query(default="all", pattern="^(all|wallet|subscription|other)$"),
    search: str = Query(default="", max_length=100),
    db: Session = Depends(get_db),
):
    query = db.query(QuotaAuditLog).filter(QuotaAuditLog.actor_type == "admin")
    if category == "wallet":
        query = query.filter(QuotaAuditLog.action.like("wallet_%"))
    elif category == "subscription":
        query = query.filter(QuotaAuditLog.subject_type == "subscription")
    elif category == "other":
        query = query.filter(
            QuotaAuditLog.subject_type != "subscription",
            ~QuotaAuditLog.action.like("wallet_%"),
        )
    term = search.strip()
    if term:
        pattern = "%" + term.replace("%", r"\%").replace("_", r"\_") + "%"
        matched_admins = [
            str(user.id) for user in db.query(User.id).filter(
                or_(User.full_name.ilike(pattern), User.email.ilike(pattern))
            ).limit(100).all()
        ]
        query = query.filter(or_(
            QuotaAuditLog.actor_id.in_(matched_admins),
            QuotaAuditLog.actor_id.ilike(pattern),
            QuotaAuditLog.subject_id.ilike(pattern),
            QuotaAuditLog.subject_type.ilike(pattern),
            QuotaAuditLog.action.ilike(pattern),
        ))
    total = query.with_entities(func.count(QuotaAuditLog.id)).scalar() or 0
    rows = (
        query.order_by(QuotaAuditLog.created_at.desc(), QuotaAuditLog.id.desc())
        .offset(offset).limit(limit).all()
    )
    actor_ids = {int(row.actor_id) for row in rows if str(row.actor_id).isdigit()}
    admins = {
        user.id: (user.full_name or user.email or f"#{user.id}")
        for user in db.query(User).filter(User.id.in_(actor_ids)).all()
    } if actor_ids else {}
    def item(row):
        actor_id = str(row.actor_id)
        when = row.created_at
        if when and when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        # Only explicitly approved audit detail keys may reach the browser.
        details = row.details if isinstance(row.details, dict) else {}
        safe_keys = {
            "origin", "amount_toman", "previous_balance_toman",
            "new_balance_toman", "previous_usage_bytes",
            "previous_traffic_limit_bytes", "new_traffic_limit_bytes",
            "previous_expiry_at", "new_expiry_at",
            "add_days", "add_traffic_gb", "reset_usage", "reset_date",
            "note", "transaction_id", "reset_at",
            "method", "route", "http_status",
        }
        safe = {key: details[key] for key in safe_keys if key in details}
        return {
            "id": row.id,
            "actor": admins.get(int(actor_id), actor_id) if actor_id.isdigit() else actor_id,
            "actor_id": actor_id,
            "action": row.action,
            "subject_type": row.subject_type,
            "subject_id": row.subject_id,
            "success": row.success,
            "created_at": when.isoformat() if when else None,
            "details": safe,
        }
    return {"items": [item(row) for row in rows], "total": int(total), "limit": limit, "offset": offset}

@router.get("/stats")
def admin_activity_stats(db: Session = Depends(get_db)):
    rows = db.query(
        QuotaAuditLog.action, func.count(QuotaAuditLog.id)
    ).filter(QuotaAuditLog.actor_type == "admin").group_by(QuotaAuditLog.action).all()
    summary = {str(action): int(count) for action, count in rows}
    return {
        "recorded_total": sum(summary.values()),
        "wallet_adjustments": sum(count for action, count in summary.items() if action.startswith("wallet_")),
        "subscription_changes": sum(count for action, count in summary.items() if action.startswith("subscription_")),
        "by_action": summary,
        "scope": "recorded_admin_audit_events_only",
    }
