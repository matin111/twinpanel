"""Read-only protocol limits derived from the owning panel's plan type.

The client never invents commercial entitlements from a displayed plan name.
Explicit plan protocol rows remain authoritative; the legacy Vitory type
has a strict two-family ceiling to prevent old copied 16-protocol accounts
from advertising unsupported connections.
"""
from __future__ import annotations


VITORY_PROTOCOLS = frozenset({"v2ray", "hysteria2"})


def category_protocols(
    subscription_type: str | None,
    configured_protocols: set[str],
) -> set[str]:
    normalized = " ".join(str(subscription_type or "").split()).casefold()
    vitory = (
        "ویتوری" in normalized or
        "vitory" in normalized or
        "v2ray" in normalized
    )
    if vitory:
        return set(configured_protocols & VITORY_PROTOCOLS) if configured_protocols else set(VITORY_PROTOCOLS)
    # Empty means a historic plan lacking an explicit template; its
    # own SubscriptionProtocol rows remain the authorization boundary.
    return set(configured_protocols)
