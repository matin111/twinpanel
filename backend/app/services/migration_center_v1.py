from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Iterable


SUPPORTED_SOURCES = ("sanaei", "marzban", "pasargad")

_USERNAME_KEYS = ("username", "email", "name", "user")
_LEGACY_URL_KEYS = (
    "subscription_url",
    "sub_url",
    "subscriptionUrl",
    "legacy_subscription_url",
)
_CREDENTIAL_KEYS = (
    "password",
    "passwd",
    "uuid",
    "token",
    "secret",
    "private_key",
    "public_key",
    "config",
    "config_text",
)
_SOURCE_ID_KEYS = ("source_id", "id", "uuid", "username", "email")


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _first(record: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in record and _nonempty(record[key]):
            return record[key]
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _expand_sanaei(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a 3x-ui/Sanaei inbound export without mutating the source payload.

    Sanaei commonly stores clients inside an inbound ``settings`` JSON object.
    Direct client-shaped records are accepted unchanged. No network lookup or
    credential generation is performed here.
    """
    settings = _json_object(record.get("settings"))
    clients = settings.get("clients")
    if not isinstance(clients, list):
        return [deepcopy(record)]

    expanded: list[dict[str, Any]] = []
    for client in clients:
        if not isinstance(client, dict):
            continue
        candidate = deepcopy(client)
        candidate.setdefault("inbound_id", record.get("id"))
        candidate.setdefault("inbound_remark", record.get("remark"))
        expanded.append(candidate)
    return expanded or [deepcopy(record)]


def _expand_marzban(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Accept either one Marzban user or an export envelope containing users."""
    users = record.get("users")
    if isinstance(users, list):
        rows = [deepcopy(item) for item in users if isinstance(item, dict)]
        return rows or [deepcopy(record)]
    if isinstance(users, dict):
        rows: list[dict[str, Any]] = []
        for key, value in users.items():
            if isinstance(value, dict):
                item = deepcopy(value)
                item.setdefault("username", key)
                rows.append(item)
        return rows or [deepcopy(record)]
    return [deepcopy(record)]


def _expand_record(source: str, record: dict[str, Any]) -> list[dict[str, Any]]:
    if source == "sanaei":
        return _expand_sanaei(record)
    if source == "marzban":
        return _expand_marzban(record)
    return [deepcopy(record)]


def _credentials(source: str, record: dict[str, Any]) -> dict[str, Any]:
    """Copy existing credential values exactly; never derive or regenerate them."""
    preserved: dict[str, Any] = {}

    nested = _as_dict(record.get("credentials"))
    for key, value in nested.items():
        if _nonempty(value):
            preserved[key] = deepcopy(value)

    for key in _CREDENTIAL_KEYS:
        if key in record and _nonempty(record[key]):
            preserved.setdefault(key, deepcopy(record[key]))

    # Sanaei/3x-ui client exports use ``id`` as the existing client UUID. Keep
    # the exact value, but expose its semantic meaning in the normalized report.
    if source == "sanaei" and _nonempty(record.get("id")):
        preserved.setdefault("uuid", deepcopy(record["id"]))

    # Marzban exports can expose protocol links as the effective client material.
    links = record.get("links")
    if isinstance(links, list) and links:
        preserved.setdefault("links", deepcopy(links))

    return preserved


def normalize_record(source: str, record: dict[str, Any], index: int) -> dict[str, Any]:
    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"unsupported migration source: {source}")
    if not isinstance(record, dict):
        raise ValueError("migration record must be an object")

    username = _first(record, _USERNAME_KEYS)
    legacy_url = _first(record, _LEGACY_URL_KEYS)
    credentials = _credentials(source, record)
    source_id = _first(record, _SOURCE_ID_KEYS)

    warnings: list[str] = []
    if not _nonempty(username):
        warnings.append("missing_username")
    if not credentials:
        warnings.append("missing_existing_credentials")
    if not _nonempty(legacy_url):
        warnings.append("missing_legacy_subscription_url")

    return {
        "index": index,
        "source": source,
        "source_id": source_id,
        "username": username,
        "credentials": credentials,
        "legacy_subscription_url": legacy_url,
        "preservation": {
            "credentials": "preserve_existing" if credentials else "not_present",
            "subscription_url": "preserve_existing" if _nonempty(legacy_url) else "not_present",
        },
        "ready_for_future_import": not warnings,
        "warnings": warnings,
    }


def dry_run_migration(source: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Produce a compatibility report only.

    This function is intentionally stateless: it has no database/session
    dependency, performs no provisioning, and never generates credentials.
    """
    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"unsupported migration source: {source}")

    expanded: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("migration record must be an object")
        expanded.extend(_expand_record(source, record))

    normalized = [
        normalize_record(source, record, index)
        for index, record in enumerate(expanded)
    ]
    ready = sum(1 for item in normalized if item["ready_for_future_import"])

    return {
        "dry_run": True,
        "writes_performed": False,
        "source": source,
        "summary": {
            "input_records": len(records),
            "expanded_records": len(normalized),
            "ready_records": ready,
            "warning_records": len(normalized) - ready,
        },
        "records": normalized,
    }
