"""Stable, collision-resistant client namespaces for TwinPanel and resellers.

A tenant namespace is derived from its installation UUID. No reseller identity,
license key, subscriber username or password is sent to the vendor for lookup.
The global directory indexes only the first namespace segment.
"""
from __future__ import annotations

import hashlib
import re

_NAMESPACE_RE = re.compile(r"^TP[A-F0-9]{16}$")
_OTHER_ALIAS_RE = re.compile(r"^TP[A-F0-9]{16}_", re.IGNORECASE)


def installation_namespace(installation_id: str) -> str:
    value = str(installation_id or "").strip()
    if not value or len(value) > 180:
        raise ValueError("installation_id_invalid")
    digest = hashlib.sha256(
        ("twinpanel:central-app:v1:" + value).encode("utf-8")
    ).hexdigest()[:16].upper()
    return "TP" + digest


def reseller_prefix(installation_id: str, reseller_id: int) -> str:
    ident = int(reseller_id)
    if ident <= 0:
        raise ValueError("reseller_id_invalid")
    return f"{installation_namespace(installation_id)}_R{ident:X}_"


def prefix_account_name(installation_id: str, reseller_id: int, name: str) -> str:
    """Only prefix new reseller subscriptions; existing usernames are untouched."""
    prefix = reseller_prefix(installation_id, reseller_id)
    name = str(name or "").strip()
    if name.startswith(prefix):
        return name
    if not name or _OTHER_ALIAS_RE.match(name):
        raise ValueError("username_prefix_conflict")
    if any(ch.isspace() for ch in name) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ValueError("username_invalid_for_vpn")
    result = prefix + name
    # Keep protocol usernames within a conservative, portable bound.
    if len(result) > 64:
        raise ValueError("username_too_long_for_vpn")
    return result


def central_app_entitled() -> bool:
    """Fail closed unless a local vendor-signed unexpired app license exists."""
    from .system_release import _verify_entitlement, load_license_state
    state = load_license_state()
    if str(state.get("status") or "").strip().lower() in {
        "revoked", "suspended", "expired", "license_expired", "trial_expired",
    }:
        return False
    if str(state.get("validation") or "").strip().lower() in {
        "none", "server_unreachable",
    }:
        return False
    token = str(state.get("signed_entitlement") or "").strip()
    if not token:
        return False
    try:
        verified = _verify_entitlement(token)
    except Exception:
        return False
    return bool(
        verified.get("app_enabled") is True
        and "central_app" in (verified.get("features") or [])
        and verified.get("status") == "active"
    )
