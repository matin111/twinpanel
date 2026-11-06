"""Read-only XHTTP REALITY SNI reconciliation for existing customer links.

When the admin applies a new REALITY SNI on an Exit node, the authoritative
modern_protocol_settings row changes but historically provisioned encrypted
VLESS URIs still contain the previous name. Never modify user UUIDs, keys,
other protocol credentials or the Xray service during public delivery.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qsl, quote, urlsplit

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

_REALITY_SNI = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{1,251}[A-Za-z0-9])$"
)
_QUERY_SNI = re.compile(r"(?P<separator>[?&])sni=[^&#]*")


def _safe_name(value: Any) -> str:
    name = str(value or "").strip().lower()
    if (
        len(name) < 4
        or len(name) > 253
        or not _REALITY_SNI.fullmatch(name)
        or ".." in name
        or "." not in name
    ):
        return ""
    return name


def applied_reality_snis(db: Session) -> dict[int, str]:
    """One cheap read for all nodes; settings are written after server apply.

    The admin API commits these fields only after the target Xray config has
    been validated and activated. The additional target/name consistency
    check rejects stale or incomplete settings.
    """
    try:
        rows = db.execute(
            text(
                "SELECT node_id, settings_json FROM modern_protocol_settings "
                "WHERE protocol='v2ray'"
            )
        ).all()
    except SQLAlchemyError:
        # Old installations may not yet have the optional settings table.
        return {}

    names: dict[int, str] = {}
    for node_id, raw in rows:
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(data, dict):
                continue
            name = _safe_name(data.get("reality_server_name"))
            target = str(data.get("reality_target") or "").strip().lower()
            if name and target == name + ":443":
                names[int(node_id)] = name
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return names


def _correct_xhttp_uri(uri: str, reality_sni: str) -> str:
    if not isinstance(uri, str) or not uri.startswith("vless://"):
        return uri
    try:
        parts = urlsplit(uri)
        fields = parse_qsl(parts.query, keep_blank_values=True)
        options = dict(fields)
    except ValueError:
        return uri
    if (
        options.get("type") != "xhttp"
        or options.get("security") != "reality"
        or sum(key == "sni" for key, _ in fields) != 1
    ):
        return uri
    if options["sni"].lower() == reality_sni:
        return uri
    # Preserve the COMPLETE original URI byte-for-byte except the SNI value:
    # UUID, port, REALITY public key, shortId, path, mode, and fragment intact.
    return _QUERY_SNI.sub(
        lambda match: match.group("separator") + "sni=" + quote(reality_sni, safe=""),
        uri,
        count=1,
    )


def rewrite_reality_sni_item(
    item: dict[str, Any],
    reality_sni: str | None,
) -> dict[str, Any]:
    name = _safe_name(reality_sni)
    if not name or not isinstance(item, dict):
        return item

    profiles = item.get("profiles")
    if not isinstance(profiles, list):
        return item

    result = dict(item)
    replacements: list[Any] = []
    changed = False

    for profile in profiles:
        if (
            not isinstance(profile, dict)
            or str(profile.get("id") or "").lower() != "xhttp_reality"
        ):
            replacements.append(profile)
            continue
        uri = str(profile.get("uri") or "")
        updated = _correct_xhttp_uri(uri, name)
        if updated == uri:
            replacements.append(profile)
            continue
        copy = dict(profile)
        copy["uri"] = updated
        copy["sni"] = name
        # The old QR image would otherwise still contain the obsolete URI.
        copy.pop("qr", None)
        replacements.append(copy)
        changed = True

    if not changed:
        return item

    result["profiles"] = replacements
    original_primary = str(item.get("uri") or "")
    rewritten_primary = _correct_xhttp_uri(original_primary, name)
    if rewritten_primary != original_primary:
        result["uri"] = rewritten_primary
        result["sni"] = name
        result.pop("qr", None)
    return result
