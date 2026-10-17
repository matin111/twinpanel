from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .system_release import license_allows_mutation, license_enforced


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# Existing VPN data-plane services are intentionally not touched by this guard.
# Only panel/API management mutations are restricted after an authoritative
# trial/license expiry.
PROTECTED_PREFIXES = (
    "/v1/admin/",
    "/v1/nodes",
    "/v1/tunnels",
    "/v1/plans",
    "/v1/subscriptions",
    "/v1/provision",
    "/v1/domains",
    "/v1/branding",
    "/v1/settings",
)

# License activation, backup/export and diagnostics stay usable after expiry.
ALLOWED_MUTATION_PREFIXES = (
    "/v1/admin/system/license",
    "/v1/admin/backups",
)


class LicenseMutationGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method.upper() in SAFE_METHODS:
            return await call_next(request)

        if not license_enforced():
            return await call_next(request)

        path = request.url.path

        if path.startswith(ALLOWED_MUTATION_PREFIXES):
            return await call_next(request)

        protected = any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)
        if not protected:
            return await call_next(request)

        if license_allows_mutation():
            return await call_next(request)

        return JSONResponse(
            status_code=402,
            content={
                "detail": "TWINPANEL_LICENSE_REQUIRED",
                "message_fa": "دوره آزمایشی یا لایسنس پنل پایان یافته است. برای ادامه مدیریت، لایسنس را فعال کنید.",
                "message_en": "The TwinPanel trial or license has expired. Activate a license to continue management operations.",
            },
        )
