"""Best-effort metadata-only audit for authenticated admin mutations.

Detailed financial deltas are emitted by the authoritative business handlers;
the general guard records operation metadata without secrets or request bodies.
Never blocks or rolls back the underlying request if auditing fails.
"""
from __future__ import annotations

import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

from .database import SessionLocal
from .models import User, UserRole
from .quota_models import QuotaAuditLog
from .security import decode_access_token

_MUTATIONS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Only business mutations with a recognizable human meaning belong in the
# customer-facing administrator history. Infrastructure checks, support replies,
# and unclassified routes are intentionally excluded.
_BUSINESS_ACTIONS = (
    (re.compile(r"^/v1/subscriptions/(\d+)/admin-edit$"), "subscription_edit", "subscription"),
    (re.compile(r"^/v1/subscriptions/(\d+)/reset-usage$"), "subscription_usage_reset", "subscription"),
    (re.compile(r"^/v1/admin/users/(\d+)$"), "user_edit", "user"),
    (re.compile(r"^/v1/users/(\d+)$"), "user_edit", "user"),
)
_DETAILED = (
    re.compile(r"^/v1/admin/wallet/wallets/\d+/adjust$"),
    re.compile(r"^/v1/subscriptions/\d+/extend$"),
)


class AdminMutationAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        matched = next(
            ((pattern.match(path), action, subject) for pattern, action, subject
             in _BUSINESS_ACTIONS if pattern.match(path)),
            None,
        )
        if (
            request.method not in _MUTATIONS
            or response.status_code >= 400
            or matched is None
            or any(pattern.match(path) for pattern in _DETAILED)
        ):
            return response

        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            return response
        try:
            subject = decode_access_token(header[7:].strip())
        except Exception:
            return response
        if not subject:
            return response
        # No request bodies, passwords, query strings or tokens are retained.
        match, action, category = matched
        target_id = match.group(1)
        try:
            with SessionLocal() as db:
                user = db.get(User, int(subject))
                if not user or not user.is_active or user.role != UserRole.ADMIN:
                    return response
                db.add(QuotaAuditLog(
                    actor_type="admin",
                    actor_id=str(user.id),
                    action=action,
                    subject_type=category,
                    subject_id=target_id,
                    request_id=str(uuid.uuid4()),
                    details={
                        "method": request.method,
                        "http_status": int(response.status_code),
                    },
                    success=True,
                ))
                db.commit()
        except Exception:
            # Auditing must never make a successful operational action fail.
            pass
        return response
