from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
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
_CANONICAL_STATE_KEYS = (
    "traffic_limit_bytes",
    "traffic_used_bytes",
    "starts_at",
    "expires_at",
    "activation_duration_days",
)


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


def _present_int(record: dict[str, Any], key: str) -> tuple[bool, int | None]:
    if key not in record:
        return False, None
    raw = record.get(key)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return False, None
    try:
        return True, int(raw)
    except (TypeError, ValueError):
        return True, None


def _unix_iso(value: int, *, milliseconds: bool) -> str:
    timestamp = value / 1000 if milliseconds else value
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _expand_sanaei(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a 3x-ui/Sanaei inbound export without mutating the source payload.

    Sanaei commonly stores clients inside an inbound ``settings`` JSON object
    while per-client traffic counters live in ``clientStats``. Match those
    counters by the existing client email; never generate or rewrite identity.
    """
    settings = _json_object(record.get("settings"))
    clients = settings.get("clients")
    if not isinstance(clients, list):
        return [deepcopy(record)]

    stats_by_email: dict[str, dict[str, Any]] = {}
    client_stats = record.get("clientStats")
    if isinstance(client_stats, list):
        for item in client_stats:
            if not isinstance(item, dict):
                continue
            email = str(item.get("email") or "").strip()
            if email:
                stats_by_email[email] = item

    expanded: list[dict[str, Any]] = []
    for client in clients:
        if not isinstance(client, dict):
            continue
        candidate = deepcopy(client)
        candidate.setdefault("inbound_id", record.get("id"))
        candidate.setdefault("inbound_remark", record.get("remark"))
        email = str(candidate.get("email") or "").strip()
        stat = stats_by_email.get(email)
        if stat:
            for key in ("up", "down"):
                if key not in candidate and key in stat:
                    candidate[key] = deepcopy(stat[key])
            if "expiryTime" not in candidate and "expiryTime" in stat:
                candidate["expiryTime"] = deepcopy(stat["expiryTime"])
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


def _migration_state(source: str, record: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Extract source account state while preserving absent-vs-zero semantics."""
    state: dict[str, Any] = {}
    warnings: list[str] = []

    # A normalized Dry-run record is sent back to Phase 2 by the admin UI.
    # Preserve canonical fields exactly so explicit zero/null values survive.
    for key in _CANONICAL_STATE_KEYS:
        if key in record:
            state[key] = deepcopy(record[key])

    if source == "sanaei":
        if "traffic_limit_bytes" not in state:
            present, value = _present_int(record, "totalGB")
            if present:
                if value is None or value < 0:
                    warnings.append("invalid_totalGB")
                else:
                    state["traffic_limit_bytes"] = value

        if "traffic_used_bytes" not in state:
            up_present, up = _present_int(record, "up")
            down_present, down = _present_int(record, "down")
            if up_present or down_present:
                if (up_present and (up is None or up < 0)) or (down_present and (down is None or down < 0)):
                    warnings.append("invalid_traffic_counters")
                else:
                    state["traffic_used_bytes"] = (up or 0) + (down or 0)

        if "expires_at" not in state:
            present, expiry_ms = _present_int(record, "expiryTime")
            if present:
                if expiry_ms is None:
                    warnings.append("invalid_expiryTime")
                elif expiry_ms > 0:
                    try:
                        state["expires_at"] = _unix_iso(expiry_ms, milliseconds=True)
                    except (OverflowError, OSError, ValueError):
                        warnings.append("invalid_expiryTime")
                elif expiry_ms == 0:
                    # 3x-ui uses zero for no absolute expiration.
                    state["expires_at"] = None
                else:
                    # Negative expiry values have version-dependent first-use
                    # semantics. Do not guess or convert them into a wrong date.
                    warnings.append("unsupported_negative_expiryTime")

    elif source == "marzban":
        if "traffic_limit_bytes" not in state:
            present, value = _present_int(record, "data_limit")
            if present:
                if value is None or value < 0:
                    warnings.append("invalid_data_limit")
                else:
                    state["traffic_limit_bytes"] = value

        if "traffic_used_bytes" not in state:
            present, value = _present_int(record, "used_traffic")
            if present:
                if value is None or value < 0:
                    warnings.append("invalid_used_traffic")
                else:
                    state["traffic_used_bytes"] = value

        if "expires_at" not in state:
            present, expiry_s = _present_int(record, "expire")
            if present:
                if expiry_s is None or expiry_s < 0:
                    warnings.append("invalid_expire")
                elif expiry_s > 0:
                    try:
                        state["expires_at"] = _unix_iso(expiry_s, milliseconds=False)
                    except (OverflowError, OSError, ValueError):
                        warnings.append("invalid_expire")
                else:
                    # Marzban zero means no absolute expiration.
                    state["expires_at"] = None

    return state, warnings


def normalize_record(source: str, record: dict[str, Any], index: int) -> dict[str, Any]:
    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"unsupported migration source: {source}")
    if not isinstance(record, dict):
        raise ValueError("migration record must be an object")

    username = _first(record, _USERNAME_KEYS)
    legacy_url = _first(record, _LEGACY_URL_KEYS)
    credentials = _credentials(source, record)
    source_id = _first(record, _SOURCE_ID_KEYS)
    migration_state, state_warnings = _migration_state(source, record)

    warnings: list[str] = list(state_warnings)
    blocking_warnings: list[str] = []
    if not _nonempty(source_id):
        warnings.append("missing_source_id")
        blocking_warnings.append("missing_source_id")
    if not _nonempty(username):
        warnings.append("missing_username")
        blocking_warnings.append("missing_username")
    if not credentials:
        warnings.append("missing_existing_credentials")
        blocking_warnings.append("missing_existing_credentials")
    if not _nonempty(legacy_url):
        # Legacy subscription delivery is optional for import. Keep this visible
        # as a warning, but do not block records that otherwise contain the
        # identity and credential material required by Phase 2 import.
        warnings.append("missing_legacy_subscription_url")

    normalized = {
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
        "ready_for_future_import": not blocking_warnings,
        "warnings": warnings,
    }
    normalized.update(migration_state)
    return normalized


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
    warning_records = sum(1 for item in normalized if item["warnings"])

    return {
        "dry_run": True,
        "writes_performed": False,
        "source": source,
        "summary": {
            "input_records": len(records),
            "expanded_records": len(normalized),
            "ready_records": ready,
            "warning_records": warning_records,
        },
        "records": normalized,
    }
