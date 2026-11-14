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
_PREFIXES = (
    "/v1/admin/", "/v1/subscriptions/", "/v1/nodes/",
    "/v1/plans/", "/v1/resellers/", "/v1/tunnels/",
)
_DETAILED = (
    re.compile(r"^/v1/admin/wallet/wallets/\d+/adjust$"),
    re.compile(r"^/v1/subscriptions/\d+/extend$"),
)
_ID = re.compile(r"/(\d+)(?=/|$)")


class AdminMutationAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        if (
            request.method not in _MUTATIONS
            or not path.startswith(_PREFIXES)
            or path.startswith("/v1/admin/activity")
            or response.status_code >= 400
            or any(pattern.match(path) for pattern in _DETAILED)
        ):
            return response

        header = request.headers.get("authorization", "")
        if not header.lower().startswith("bearer "):
            return response
        subject = decode_access_token(header[7:].strip())
        if not subject:
            return response
        # No request bodies, passwords, query strings or tokens are retained.
        target = _ID.search(path)
        category = path.split("/")[2] if len(path.split("/")) > 2 else "admin"
        route = request.scope.get("route")
        template = getattr(route, "path", None)
        if not template:
            template = _ID.sub("/{id}", path)
        try:
            with SessionLocal() as db:
                user = db.get(User, int(subject))
                if not user or not user.is_active or user.role != UserRole.ADMIN:
                    return response
                db.add(QuotaAuditLog(
                    actor_type="admin",
                    actor_id=str(user.id),
                    action="manual_api_mutation",
                    subject_type=category[:48],
                    subject_id=target.group(1) if target else "-",
                    request_id=str(uuid.uuid4()),
                    details={
                        "method": request.method,
                        "route": str(template)[:200],
                        "http_status": int(response.status_code),
                    },
                    success=True,
                ))
                db.commit()
        except Exception:
            # Auditing must never make a successful operational action fail.
            pass
        return response
