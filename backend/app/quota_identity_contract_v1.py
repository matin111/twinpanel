"""Canonical quota identity guard shared by usage and session admission.

A QuotaDevice is owned by exactly one source protocol. The node telemetry
spells Cisco/Xray differently from panel credentials; normalize before
comparing. Never infer user identity from IP or from a shared transport.
"""
from __future__ import annotations

from .protocol_account_registry import ALL_PROTOCOL_SET, canonical_protocol


def quota_device_matches_protocol(device_protocol: str, event_protocol: str) -> bool:
    """Return false for unknown protocol keys and cross-protocol device IDs."""
    try:
        source = canonical_protocol(device_protocol)
        reported = canonical_protocol(event_protocol)
    except (ValueError, TypeError):
        return False
    return source in ALL_PROTOCOL_SET and source == reported
