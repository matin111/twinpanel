"""Stable, collision-resistant client namespaces for TwinPanel and resellers.

A tenant namespace is derived from its installation UUID. No reseller identity,
license key, subscriber username or password is sent to the vendor for lookup.
The global directory indexes only the first namespace segment.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

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



# Short aliases affect app logins only. VPN usernames retain full prefixes.
_APP_DIRECTORY_ALIAS_FILE = Path(
    os.getenv("TWINCONNECT_DIRECTORY_ALIAS_FILE",
              "/var/lib/twinpanel-license/app-directory-alias.json")
)
_APP_ALIAS_RE = re.compile(r"^TP(?:[A-F0-9]{6}|[A-F0-9]{8}|[A-F0-9]{10}|[A-F0-9]{12}|[A-F0-9]{14}|[A-F0-9]{16})$")


def app_directory_namespace(installation_id: str) -> str:
    legacy = installation_namespace(installation_id)
    try:
        data = json.loads(_APP_DIRECTORY_ALIAS_FILE.read_text(encoding="utf-8"))
        short = str(data.get("short_namespace") or "").upper()
        if (data.get("installation_id") == installation_id
                and _APP_ALIAS_RE.fullmatch(short)
                and legacy.startswith(short)):
            return short
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return legacy


def save_app_directory_alias(installation_id: str, short_namespace: str) -> str:
    full = installation_namespace(installation_id)
    short = str(short_namespace or "").strip().upper()
    if not _APP_ALIAS_RE.fullmatch(short) or not full.startswith(short):
        raise ValueError("DIRECTORY_ALIAS_INVALID")
    path = _APP_DIRECTORY_ALIAS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps({
        "installation_id": installation_id,
        "short_namespace": short,
    }), encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)
    return short


def app_reseller_prefix(installation_id: str, reseller_id: int) -> str:
    ident = int(reseller_id)
    if ident <= 0:
        raise ValueError("reseller_id_invalid")
    return f"{app_directory_namespace(installation_id)}_R{ident:X}_"


def app_namespace_from_username(username: str, installation_id: str) -> str:
    value = str(username or "").strip().upper()
    match = re.match(r"^(TP(?:[A-F0-9]{6}|[A-F0-9]{8}|[A-F0-9]{10}|[A-F0-9]{12}|[A-F0-9]{14}|[A-F0-9]{16}))_(?:A|R[0-9A-F]+)_(?:C[0-9]+_)?APP[0-9A-F]{16}$", value)
    full = installation_namespace(installation_id)
    if match and full.startswith(match.group(1)):
        return match.group(1)
    return app_directory_namespace(installation_id)


def subscription_app_namespace(db, sub) -> str:
    from .central_app_credential_models import SubscriptionAppCredential
    from .system_release import ensure_installation_id
    identity = ensure_installation_id()
    row = db.get(SubscriptionAppCredential, int(sub.id))
    return (app_namespace_from_username(row.app_username, identity)
            if row is not None else app_directory_namespace(identity))


def subscription_app_prefix(db, sub, reseller_id: int) -> str:
    namespace = subscription_app_namespace(db, sub)
    return f"{namespace}_R{int(reseller_id):X}_" if reseller_id else namespace + "_A_"


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
        local_name = name[len(prefix):]
        result = name
    else:
        if not name or _OTHER_ALIAS_RE.match(name):
            raise ValueError("username_prefix_conflict")
        local_name = name
        result = prefix + name
    if not local_name or any(ch.isspace() for ch in local_name) or not re.fullmatch(r"[A-Za-z0-9_.-]+", local_name):
        raise ValueError("username_invalid_for_vpn")
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
