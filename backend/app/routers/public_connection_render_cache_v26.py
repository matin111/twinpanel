from __future__ import annotations

import copy
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, TypeVar


_MARKER = "TWINPANEL_PUBLIC_CONNECT_RENDER_CACHE_V26"
_CACHE: ContextVar[dict[tuple[int, int], dict[str, Any]] | None] = ContextVar(
    "twinpanel_public_connect_render_cache_v26",
    default=None,
)
_F = TypeVar("_F", bound=Callable[..., Any])


def install_public_payload_render_cache_v26(account_delivery_module: Any) -> None:
    """Wrap Account Delivery payload generation with a request-scoped cache.

    Public Connect composes its HTML through several compatibility refiners. A
    number of them independently request the exact same Account Delivery payload,
    which regenerates expensive inline QR SVGs every time. The wrapper is inert
    unless the V26 render decorator has activated a cache for the current context.
    """

    current = getattr(account_delivery_module, "_public_payload", None)
    if not callable(current):
        raise RuntimeError("account_delivery._public_payload is unavailable")
    if getattr(current, "__twinpanel_public_connect_render_cache_v26__", False):
        return

    original = current

    @wraps(original)
    def cached_public_payload(db: Any, sub: Any) -> dict[str, Any]:
        cache = _CACHE.get()
        if cache is None:
            return original(db, sub)

        subscription_id = int(getattr(sub, "id", 0) or 0)
        key = (id(db), subscription_id)
        cached = cache.get(key)
        if cached is not None:
            # Every renderer gets an isolated object. Legacy refiners can never
            # mutate the payload consumed by a later canonical renderer.
            return copy.deepcopy(cached)

        payload = original(db, sub)
        if not isinstance(payload, dict):
            return payload

        # Store a pristine request-local snapshot, but let the first caller keep
        # the object it just built. Subsequent callers receive deep copies.
        cache[key] = copy.deepcopy(payload)
        return payload

    cached_public_payload.__twinpanel_public_connect_render_cache_v26__ = True
    cached_public_payload.__twinpanel_public_connect_render_cache_v26_marker__ = _MARKER
    account_delivery_module._public_payload = cached_public_payload


def public_connection_render_cache_v26(func: _F) -> _F:
    """Activate one isolated payload cache for exactly one Public Connect render."""

    @wraps(func)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        token = _CACHE.set({})
        try:
            return func(*args, **kwargs)
        finally:
            _CACHE.reset(token)

    return wrapped  # type: ignore[return-value]
