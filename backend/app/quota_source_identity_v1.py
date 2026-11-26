"""Never attribute a quota device's bytes/session to another protocol.

A canonical source protocol is a ledger identity, not a UI display label.
Node telemetry can use OpenConnect/Xray/NaiveProxy while the provisioned
device uses Cisco/V2Ray/Naive. Canonical aliases are explicit and finite.
"""
from __future__ import annotations

from .protocol_account_registry import canonical_protocol


def device_protocol_is_source(device_protocol: str | None, source_protocol: str | None) -> bool:
    if not device_protocol or not source_protocol:
        return False
    try:
        return canonical_protocol(device_protocol) == canonical_protocol(source_protocol)
    except (ValueError, TypeError):
        return False
