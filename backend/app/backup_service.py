from __future__ import annotations

# TWINPANEL_SELECTIVE_BACKUP_SERVICE_V1

import base64
import enum
import gzip
import hashlib
import json
import os
import stat
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.pool import NullPool

from .config import settings
from .database import engine
from .routers.telegram_manager import load_bot_token


BACKUP_FORMAT = "twinpanel-selective-backup-v1"

BACKUP_ROOT = Path(
    "/var/lib/twinpanel-backups"
)

BACKUP_KEY = Path(
    "/etc/twinpanel/backup.key"
)

SETTINGS_FILE = (
    BACKUP_ROOT / "settings.json"
)

STATE_FILE = (
    BACKUP_ROOT / "scheduler-state.json"
)


# فقط داده‌های مدیریتی و Business State.
# Runtime telemetry و queueها عمداً خارج هستند.
BACKUP_TABLES = [
    # Core settings
    "branding_settings",
    "domains",
    "payment_settings",

    # Users / security
    "users",
    "user_two_factor",
    "telegram_user_links",

    # Nodes
    "nodes",
    "node_access",
    "node_protocol_configs",
    "quota_agent_identities",

    # Plans
    "plans",

    # Tunnels
    "tunnels",
    # Subscriptions
    "subscriptions",
    "subscription_nodes",
    "subscription_protocols",
    "protocol_credentials",
    "quota_devices",

    # Store / payment
    "store_orders",
    "payment_intents",
    "payment_sms_events",
    "payment_sms_reader_devices",
    "subscription_renewal_orders",

    # Wallets
    "customer_wallets",
    "customer_wallet_transactions",
    "customer_wallet_topups",

    # Discounts
    "discount_codes",
    "discount_redemptions",

    # Resellers
    "resellers",
    "reseller_traffic_packages",
    "reseller_plan_prices",
    "reseller_customers",
    "reseller_subscriptions",
    "reseller_payment_methods",
    "reseller_bot_settings",
    "reseller_bot_orders",
    "reseller_telegram_links",
    "reseller_traffic_transactions",
    "reseller_wallet_transactions",

    # Admin-created notifications
    "user_notifications",

    # Support content editable by admin
    "support_tickets",
    "support_messages",
]


EXCLUDED_RUNTIME_TABLES = [
    "admin_panel_notifications",
    "quota_audit_logs",
    "quota_node_commands",
    "quota_cursors",
    "quota_sessions",
    "quota_usage_events",
    "telegram_notifications",
    "tunnel_peer_states",
    "reseller_notifications",
    "reseller_expiry_telegram_deliveries",
    "payment_sms_reader_pair_codes",
]


DEFAULT_SETTINGS = {
    "enabled": False,
    "frequency": "daily",
    "hour": 3,
    "minute": 0,
    "weekday": 0,
    "timezone": "Asia/Tehran",
    "send_telegram": True,
    "telegram_chat_id": "",
    "retention": 14,
}


def _now_utc() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _iso_now() -> str:
    return _now_utc().isoformat()


def ensure_backup_environment() -> None:
    BACKUP_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    os.chmod(
        BACKUP_ROOT,
        0o700,
    )

    BACKUP_KEY.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not BACKUP_KEY.exists():
        BACKUP_KEY.write_bytes(
            Fernet.generate_key()
        )

    os.chmod(
        BACKUP_KEY,
        0o600,
    )

    if not SETTINGS_FILE.exists():
        tmp = SETTINGS_FILE.with_suffix(
            ".json.tmp"
        )

        tmp.write_text(
            json.dumps(
                DEFAULT_SETTINGS,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        os.chmod(
            tmp,
            0o600,
        )

        tmp.replace(
            SETTINGS_FILE
        )


def _fernet() -> Fernet:
    ensure_backup_environment()

    return Fernet(
        BACKUP_KEY
        .read_bytes()
        .strip()
    )


def recovery_key_fingerprint() -> str:
    ensure_backup_environment()

    return hashlib.sha256(
        BACKUP_KEY
        .read_bytes()
        .strip()
    ).hexdigest()[:16]


def load_settings() -> dict[str, Any]:
    ensure_backup_environment()

    try:
        raw = json.loads(
            SETTINGS_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        raw = {}

    result = (
        DEFAULT_SETTINGS.copy()
    )

    if isinstance(raw, dict):
        result.update(raw)

    return result


def save_settings(
    value: dict[str, Any],
) -> dict[str, Any]:

    ensure_backup_environment()

    result = (
        DEFAULT_SETTINGS.copy()
    )

    result.update(value)

    tmp = SETTINGS_FILE.with_suffix(
        ".json.tmp"
    )

    tmp.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    os.chmod(
        tmp,
        0o600,
    )

    tmp.replace(
        SETTINGS_FILE
    )

    return result


def _pack(value: Any) -> Any:

    if value is None:
        return None

    if isinstance(
        value,
        (bool, int, float, str),
    ):
        return value

    if isinstance(
        value,
        enum.Enum,
    ):
        return _pack(
            value.value
        )

    if isinstance(
        value,
        (bytes, bytearray, memoryview),
    ):
        return {
            "__tp_type__": "bytes",
            "value": base64.b64encode(
                bytes(value)
            ).decode(),
        }

    if isinstance(
        value,
        datetime,
    ):
        return {
            "__tp_type__": "datetime",
            "value": value.isoformat(),
        }

    if isinstance(
        value,
        date,
    ):
        return {
            "__tp_type__": "date",
            "value": value.isoformat(),
        }

    if isinstance(
        value,
        time,
    ):
        return {
            "__tp_type__": "time",
            "value": value.isoformat(),
        }

    if isinstance(
        value,
        Decimal,
    ):
        return {
            "__tp_type__": "decimal",
            "value": str(value),
        }

    if isinstance(
        value,
        UUID,
    ):
        return {
            "__tp_type__": "uuid",
            "value": str(value),
        }

    if isinstance(
        value,
        dict,
    ):
        return {
            str(k): _pack(v)
            for k, v
            in value.items()
        }

    if isinstance(
        value,
        (list, tuple),
    ):
        return [
            _pack(item)
            for item in value
        ]

    # PostgreSQL-specific values such
    # as INET can safely round-trip
    # through their textual value.
    return {
        "__tp_type__": "str",
        "value": str(value),
    }


def _unpack(value: Any) -> Any:

    if isinstance(value, list):
        return [
            _unpack(item)
            for item in value
        ]

    if not isinstance(
        value,
        dict,
    ):
        return value

    type_name = value.get(
        "__tp_type__"
    )

    if type_name == "bytes":
        return base64.b64decode(
            value["value"]
        )

    if type_name == "datetime":
        return datetime.fromisoformat(
            value["value"]
        )

    if type_name == "date":
        return date.fromisoformat(
            value["value"]
        )

    if type_name == "time":
        return time.fromisoformat(
            value["value"]
        )

    if type_name == "decimal":
        return Decimal(
            value["value"]
        )

    if type_name == "uuid":
        return UUID(
            value["value"]
        )

    if type_name == "str":
        return value["value"]

    return {
        key: _unpack(item)
        for key, item
        in value.items()
    }


def _file_entry(
    path: Path,
) -> dict[str, Any] | None:

    try:
        if not path.is_file():
            return None

        # هیچ فایل بزرگ Runtime
        # وارد بکاپ Config نمی‌شود.
        if path.stat().st_size > (
            5 * 1024 * 1024
        ):
            return None

        return {
            "mode": stat.S_IMODE(
                path.stat().st_mode
            ),
            "data": base64.b64encode(
                path.read_bytes()
            ).decode(),
        }

    except Exception:
        return None


def _collect_admin_files(
    node_key_paths: set[str],
) -> dict[str, Any]:

    result: dict[str, Any] = {}

    candidates: set[str] = set()

    # Telegram Bot token/config
    candidates.add(
        "/etc/twinpanel-telegram-api.env"
    )

    # Admin-managed configuration
    # stored below /etc/twinpanel.
    etc_root = Path(
        "/etc/twinpanel"
    )

    if etc_root.exists():
        for path in etc_root.rglob("*"):
            if not path.is_file():
                continue

            if path == BACKUP_KEY:
                continue

            # frontend runtime address is
            # deployment config, not panel data.
            if path.name == "frontend.env":
                continue

            candidates.add(
                str(path)
            )

    # SSH private-key files referenced
    # by node_access are essential for
    # restoring server access.
    candidates.update(
        path
        for path in node_key_paths
        if path
    )

    for raw in sorted(candidates):
        path = Path(raw)

        entry = _file_entry(
            path
        )

        if entry is not None:
            result[str(path)] = entry

    return result


def _current_tables() -> list[str]:

    existing = set(
        inspect(
            engine
        ).get_table_names()
    )

    return [
        name
        for name in BACKUP_TABLES
        if name in existing
    ]


def _export_database() -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[str, int],
    set[str],
]:
    selected = (
        _current_tables()
    )

    payload: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    counts: dict[str, int] = {}

    node_key_paths: set[str] = set()

    with engine.connect() as conn:

        metadata = MetaData()

        for name in selected:

            table = Table(
                name,
                metadata,
                autoload_with=conn,
            )

            rows = list(
                conn.execute(
                    select(table)
                ).mappings()
            )

            plain_rows: list[
                dict[str, Any]
            ] = []

            for row in rows:

                plain = dict(row)

                if name == "node_access":
                    key_path = plain.get(
                        "private_key_path"
                    )

                    if key_path:
                        node_key_paths.add(
                            str(key_path)
                        )

                plain_rows.append(
                    _pack(plain)
                )

            payload[name] = (
                plain_rows
            )

            counts[name] = len(
                plain_rows
            )

    return (
        payload,
        counts,
        node_key_paths,
    )


def _meta_path(
    backup_path: Path,
) -> Path:

    return Path(
        str(backup_path)
        + ".meta.json"
    )


def _write_meta(
    backup_path: Path,
    meta: dict[str, Any],
) -> None:

    path = _meta_path(
        backup_path
    )

    tmp = Path(
        str(path) + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            meta,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    os.chmod(
        tmp,
        0o600,
    )

    tmp.replace(path)


def _read_meta(
    backup_path: Path,
) -> dict[str, Any]:

    path = _meta_path(
        backup_path
    )

    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(value, dict):
            return value

    except Exception:
        pass

    return {}


def create_backup(
    kind: str = "manual",
    send_telegram: bool = False,
    telegram_chat_id: str | None = None,
) -> dict[str, Any]:

    ensure_backup_environment()

    tables, counts, node_keys = (
        _export_database()
    )

    payload = {
        "format": BACKUP_FORMAT,
        "version": 1,
        "created_at": _iso_now(),
        "kind": kind,
        "tables": tables,
        "files": _collect_admin_files(
            node_keys
        ),
    }

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    compressed = gzip.compress(
        encoded,
        compresslevel=9,
    )

    encrypted = (
        _fernet().encrypt(
            compressed
        )
    )

    stamp = _now_utc().strftime(
        "%Y%m%d-%H%M%S"
    )

    safe_kind = "".join(
        ch
        for ch in kind
        if ch.isalnum()
        or ch in ("-", "_")
    )[:24] or "manual"

    filename = (
        f"twinpanel-{stamp}-"
        f"{safe_kind}.tpbak"
    )

    target = (
        BACKUP_ROOT / filename
    )

    tmp = Path(
        str(target) + ".tmp"
    )

    tmp.write_bytes(
        encrypted
    )

    os.chmod(
        tmp,
        0o600,
    )

    tmp.replace(
        target
    )

    meta = {
        "filename": filename,
        "created_at":
            payload["created_at"],
        "kind": kind,
        "size_bytes":
            target.stat().st_size,
        "tables":
            len(tables),
        "rows":
            sum(counts.values()),
        "row_counts":
            counts,
        "telegram_sent":
            False,
        "telegram_error":
            None,
        "key_fingerprint":
            recovery_key_fingerprint(),
        "sha256":
            hashlib.sha256(
                target.read_bytes()
            ).hexdigest(),
    }

    _write_meta(
        target,
        meta,
    )

    if send_telegram:

        chat_id = (
            telegram_chat_id
            or load_settings().get(
                "telegram_chat_id"
            )
        )

        if chat_id:
            try:
                send_backup_to_telegram(
                    target,
                    str(chat_id),
                )

                meta = _read_meta(
                    target
                )

            except Exception as exc:

                meta[
                    "telegram_error"
                ] = str(exc)[:500]

                _write_meta(
                    target,
                    meta,
                )

        else:
            meta[
                "telegram_error"
            ] = (
                "Telegram Chat ID "
                "تنظیم نشده است"
            )

            _write_meta(
                target,
                meta,
            )

    return meta


def list_backups() -> list[
    dict[str, Any]
]:

    ensure_backup_environment()

    result = []

    for path in sorted(
        BACKUP_ROOT.glob(
            "*.tpbak"
        ),
        key=lambda p:
            p.stat().st_mtime,
        reverse=True,
    ):
        meta = _read_meta(
            path
        )

        if not meta:
            meta = {
                "filename":
                    path.name,
                "created_at":
                    datetime.fromtimestamp(
                        path.stat().st_mtime,
                        tz=timezone.utc,
                    ).isoformat(),
                "kind":
                    "imported",
                "size_bytes":
                    path.stat().st_size,
                "telegram_sent":
                    False,
            }

        result.append(
            meta
        )

    return result


def get_backup_path(
    filename: str,
) -> Path:

    safe = Path(
        filename
    ).name

    if (
        safe != filename
        or not safe.endswith(
            ".tpbak"
        )
    ):
        raise ValueError(
            "Invalid backup filename"
        )

    path = (
        BACKUP_ROOT / safe
    )

    if not path.is_file():
        raise FileNotFoundError(
            safe
        )

    return path


def delete_backup(
    filename: str,
) -> None:

    path = get_backup_path(
        filename
    )

    path.unlink(
        missing_ok=True
    )

    _meta_path(
        path
    ).unlink(
        missing_ok=True
    )


def _decode_backup(
    path: Path,
) -> dict[str, Any]:

    try:
        compressed = (
            _fernet().decrypt(
                path.read_bytes()
            )
        )

    except InvalidToken as exc:
        raise ValueError(
            "کلید این بکاپ با "
            "کلید بازیابی سرور "
            "مطابقت ندارد"
        ) from exc

    try:
        raw = gzip.decompress(
            compressed
        )

        payload = json.loads(
            raw.decode("utf-8")
        )

    except Exception as exc:
        raise ValueError(
            "ساختار فایل بکاپ "
            "معتبر نیست"
        ) from exc

    if (
        not isinstance(
            payload,
            dict,
        )
        or payload.get(
            "format"
        ) != BACKUP_FORMAT
        or not isinstance(
            payload.get(
                "tables"
            ),
            dict,
        )
    ):
        raise ValueError(
            "این فایل بکاپ "
            "TwinPanel معتبر نیست"
        )

    unknown = (
        set(
            payload["tables"]
        )
        - set(
            BACKUP_TABLES
        )
    )

    if unknown:
        raise ValueError(
            "Backup contains "
            "unsupported tables: "
            + ", ".join(
                sorted(unknown)
            )
        )

    return payload


def inspect_backup(
    path: Path,
) -> dict[str, Any]:

    payload = _decode_backup(
        path
    )

    counts = {
        name: len(rows)
        for name, rows
        in payload[
            "tables"
        ].items()
    }

    return {
        "format":
            payload["format"],
        "created_at":
            payload.get(
                "created_at"
            ),
        "kind":
            payload.get(
                "kind"
            ),
        "tables":
            len(counts),
        "rows":
            sum(counts.values()),
        "row_counts":
            counts,
        "files":
            len(
                payload.get(
                    "files"
                ) or {}
            ),
    }


def import_backup_file(
    source: Path,
    original_name: str,
) -> dict[str, Any]:

    ensure_backup_environment()

    info = inspect_backup(
        source
    )

    stamp = _now_utc().strftime(
        "%Y%m%d-%H%M%S"
    )

    base = Path(
        original_name
    ).name

    if not base.endswith(
        ".tpbak"
    ):
        base = (
            f"twinpanel-import-"
            f"{stamp}.tpbak"
        )

    target = (
        BACKUP_ROOT / base
    )

    if target.exists():
        target = (
            BACKUP_ROOT
            / (
                f"{target.stem}-"
                f"{stamp}.tpbak"
            )
        )

    target.write_bytes(
        source.read_bytes()
    )

    os.chmod(
        target,
        0o600,
    )

    meta = {
        "filename":
            target.name,
        "created_at":
            info.get(
                "created_at"
            ) or _iso_now(),
        "kind":
            "imported",
        "size_bytes":
            target.stat().st_size,
        "tables":
            info["tables"],
        "rows":
            info["rows"],
        "row_counts":
            info["row_counts"],
        "telegram_sent":
            False,
        "telegram_error":
            None,
        "key_fingerprint":
            recovery_key_fingerprint(),
        "sha256":
            hashlib.sha256(
                target.read_bytes()
            ).hexdigest(),
    }

    _write_meta(
        target,
        meta,
    )

    return meta



# TWINPANEL_BACKUP_TELEGRAM_VERIFY_V3
def _telegram_safe_error(
    description: str | None,
    status_code: int,
) -> str:

    text = str(
        description
        or f"HTTP {status_code}"
    ).strip()

    lower = text.lower()

    if "chat not found" in lower:
        return (
            "گروه یا کانال پیدا نشد. "
            "Chat ID را بررسی کنید و مطمئن شوید "
            "ربات به همان گروه یا کانال اضافه شده است."
        )

    if (
        "bot was kicked" in lower
        or "bot is not a member" in lower
    ):
        return (
            "ربات عضو این گروه یا کانال نیست. "
            "ربات را دوباره اضافه کنید."
        )

    if (
        "not enough rights" in lower
        or "have no rights" in lower
        or "need administrator" in lower
        or "forbidden" in lower
    ):
        return (
            "ربات اجازه ارسال پیام یا فایل را ندارد. "
            "در کانال، ربات را Administrator کنید و "
            "اجازه Post Messages بدهید."
        )

    if "chat_write_forbidden" in lower:
        return (
            "ارسال پیام در این چت برای ربات ممنوع است."
        )

    return (
        "خطای Telegram: "
        + text[:240]
    )


def _telegram_api_call(
    token: str,
    method: str,
    *,
    data: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:

    try:
        response = httpx.post(
            (
                "https://api.telegram.org/"
                f"bot{token}/{method}"
            ),
            data=data or {},
            files=files,
            timeout=timeout,
        )

    except httpx.RequestError as exc:
        raise RuntimeError(
            "اتصال به Telegram API برقرار نشد."
        ) from exc

    try:
        payload = response.json()

    except Exception:
        payload = {}

    if (
        response.status_code >= 400
        or not payload.get("ok")
    ):
        raise RuntimeError(
            _telegram_safe_error(
                payload.get("description"),
                response.status_code,
            )
        )

    return payload


def verify_telegram_chat(
    chat_id: str,
    *,
    send_probe: bool = True,
) -> dict[str, Any]:

    chat_id = str(chat_id or "").strip()

    if not chat_id:
        raise RuntimeError(
            "Telegram Chat ID وارد نشده است."
        )

    token = load_bot_token()

    me_payload = _telegram_api_call(
        token,
        "getMe",
    )

    bot_info = (
        me_payload.get("result")
        or {}
    )

    chat_payload = _telegram_api_call(
        token,
        "getChat",
        data={
            "chat_id": chat_id,
        },
    )

    chat = (
        chat_payload.get("result")
        or {}
    )

    chat_type = str(
        chat.get("type")
        or ""
    ).strip()

    allowed_types = {
        "group",
        "supergroup",
        "channel",
    }

    if chat_type not in allowed_types:
        raise RuntimeError(
            "این Chat ID متعلق به گروه، "
            "سوپرگروه یا کانال نیست."
        )

    if send_probe:
        _telegram_api_call(
            token,
            "sendMessage",
            data={
                "chat_id": chat_id,
                "text": (
                    "✅ اتصال بکاپ TwinPanel "
                    "با موفقیت تأیید شد."
                ),
            },
        )

    return {
        "ok": True,
        "verified": True,
        "chat_id": str(
            chat.get("id")
            or chat_id
        ),
        "title": (
            chat.get("title")
            or ""
        ),
        "type": chat_type,
        "bot_username": (
            bot_info.get("username")
            or ""
        ),
        "probe_sent": bool(
            send_probe
        ),
    }



def send_backup_to_telegram(
    backup_path: Path,
    chat_id: str,
) -> dict[str, Any]:

    token = load_bot_token()

    meta = _read_meta(
        backup_path
    )

    caption = (
        "TwinPanel Backup\n"
        f"نوع: {meta.get('kind','backup')}\n"
        f"زمان: {meta.get('created_at','')}\n"
        "فایل رمزگذاری‌شده است."
    )

    with backup_path.open(
        "rb"
    ) as handle:

        payload = _telegram_api_call(
            token,
            "sendDocument",
            data={
                "chat_id":
                    str(chat_id),
                "caption":
                    caption,
            },
            files={
                "document": (
                    backup_path.name,
                    handle,
                    "application/octet-stream",
                )
            },
            timeout=180.0,
        )

    result = (
        payload.get("result")
        or {}
    )

    return {
        "ok": True,
        "chat_id": str(chat_id),
        "message_id":
            result.get("message_id"),
    }


def test_telegram(
    chat_id: str,
) -> dict[str, Any]:

    verification = (
        verify_telegram_chat(
            chat_id,
            send_probe=False,
        )
    )

    token = load_bot_token()

    _telegram_api_call(
        token,
        "sendMessage",
        data={
            "chat_id":
                str(chat_id),
            "text": (
                "🧪 تست ارسال بکاپ TwinPanel\n"
                "اتصال تلگرام فعال است."
            ),
        },
    )

    return {
        **verification,
        "test_message_sent": True,
    }

def _dependency_order(
    names: list[str],
    conn,
) -> list[str]:

    selected = set(
        names
    )

    inspector = inspect(
        conn
    )

    dependencies: dict[
        str,
        set[str],
    ] = {}

    for name in names:

        deps = set()

        for fk in (
            inspector
            .get_foreign_keys(
                name
            )
        ):
            parent = fk.get(
                "referred_table"
            )

            if (
                parent
                and parent
                in selected
                and parent != name
            ):
                deps.add(
                    parent
                )

        dependencies[
            name
        ] = deps

    ordered: list[str] = []

    pending = set(
        names
    )

    while pending:

        ready = sorted(
            name
            for name in pending
            if not (
                dependencies[
                    name
                ]
                & pending
            )
        )

        if not ready:
            # No cycle currently exists in
            # the known schema, but keep a
            # deterministic fallback.
            ready = [
                sorted(pending)[0]
            ]

        for name in ready:
            ordered.append(
                name
            )

            pending.remove(
                name
            )

    return ordered


def _restore_extra_files(
    files: dict[str, Any],
) -> None:

    if not isinstance(
        files,
        dict,
    ):
        return

    for raw_path, entry in (
        files.items()
    ):

        if not isinstance(
            entry,
            dict,
        ):
            continue

        path = Path(
            raw_path
        )

        allowed = (
            raw_path
            == "/etc/twinpanel-telegram-api.env"
            or raw_path.startswith(
                "/etc/twinpanel/"
            )
            or raw_path.startswith(
                "/root/"
            )
            or raw_path.startswith(
                "/home/"
            )
        )

        if not allowed:
            continue

        try:
            data = base64.b64decode(
                entry["data"]
            )

            path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            tmp = Path(
                str(path) + ".restore"
            )

            tmp.write_bytes(
                data
            )

            mode = int(
                entry.get(
                    "mode",
                    0o600,
                )
            )

            os.chmod(
                tmp,
                mode,
            )

            tmp.replace(
                path
            )

        except Exception as exc:
            raise RuntimeError(
                "Restore config file "
                f"failed: {raw_path}: "
                f"{exc}"
            ) from exc


def _reset_sequences(
    conn,
    tables: dict[str, Table],
) -> None:

    for name, table in (
        tables.items()
    ):

        for column in (
            table.columns
        ):

            try:
                sequence = (
                    conn.execute(
                        text(
                            "SELECT "
                            "pg_get_serial_sequence"
                            "(:table_name,"
                            ":column_name)"
                        ),
                        {
                            "table_name":
                                f"public.{name}",
                            "column_name":
                                column.name,
                        },
                    )
                    .scalar()
                )

            except Exception:
                sequence = None

            if not sequence:
                continue

            maximum = (
                conn.execute(
                    select(
                        column
                    ).order_by(
                        column.desc()
                    ).limit(1)
                ).scalar()
            )

            if maximum is None:
                conn.execute(
                    text(
                        "SELECT setval("
                        "CAST(:seq AS regclass),"
                        "1,false)"
                    ),
                    {
                        "seq":
                            sequence,
                    },
                )
            else:
                try:
                    value = int(
                        maximum
                    )
                except Exception:
                    continue

                conn.execute(
                    text(
                        "SELECT setval("
                        "CAST(:seq AS regclass),"
                        ":value,true)"
                    ),
                    {
                        "seq":
                            sequence,
                        "value":
                            value,
                    },
                )


def restore_backup(
    filename: str,
) -> dict[str, Any]:

    backup_path = get_backup_path(
        filename
    )

    payload = _decode_backup(
        backup_path
    )

    # همیشه قبل از Restore
    # یک Safety Backup مستقل.
    safety = create_backup(
        kind="pre-restore",
        send_telegram=False,
    )

    current = set(
        _current_tables()
    )

    restore_names = [
        name
        for name in BACKUP_TABLES
        if (
            name in current
            and name
            in payload["tables"]
        )
    ]

    if not restore_names:
        raise RuntimeError(
            "هیچ جدول قابل Restore "
            "داخل بکاپ وجود ندارد"
        )

    # TWINPANEL_RESTORE_ISOLATED_DB_V1
    # Restore must never consume or block the
    # normal API QueuePool.
    restore_engine = create_engine(
        settings.database_url,
        poolclass=NullPool,
        pool_pre_ping=True,
        future=True,
    )

    with restore_engine.begin() as conn:

        # Never allow TRUNCATE/restore to wait
        # indefinitely behind live API traffic.
        conn.execute(
            text(
                "SET LOCAL lock_timeout = '10s'"
            )
        )

        conn.execute(
            text(
                "SET LOCAL statement_timeout = '90s'"
            )
        )

        metadata = MetaData()

        reflected: dict[
            str,
            Table,
        ] = {}

        for name in restore_names:

            reflected[name] = Table(
                name,
                metadata,
                autoload_with=conn,
            )

        order = (
            _dependency_order(
                restore_names,
                conn,
            )
        )

        quoted = ",".join(
            '"' + name.replace(
                '"',
                '""',
            ) + '"'
            for name
            in restore_names
        )

        # Runtime dependent tables may
        # be cleared by CASCADE.
        # They are intentionally not
        # part of the backup.
        conn.execute(
            text(
                "TRUNCATE TABLE "
                + quoted
                + " RESTART IDENTITY "
                  "CASCADE"
            )
        )

        for name in order:

            table = reflected[
                name
            ]

            raw_rows = (
                payload["tables"]
                .get(
                    name,
                    [],
                )
            )

            rows = [
                _unpack(row)
                for row
                in raw_rows
            ]

            for start in range(
                0,
                len(rows),
                500,
            ):
                batch = rows[
                    start:
                    start + 500
                ]

                if batch:
                    conn.execute(
                        table.insert(),
                        batch,
                    )

        _reset_sequences(
            conn,
            reflected,
        )

    # External files are restored only
    # after DB transaction succeeds.
    _restore_extra_files(
        payload.get(
            "files"
        ) or {}
    )

    engine.dispose()

    return {
        "ok": True,
        "restored":
            filename,
        "tables":
            len(restore_names),
        "rows":
            sum(
                len(
                    payload[
                        "tables"
                    ].get(
                        name,
                        [],
                    )
                )
                for name
                in restore_names
            ),
        "safety_backup":
            safety[
                "filename"
            ],
    }


def cleanup_retention(
    retention: int,
) -> None:

    try:
        keep = max(
            1,
            min(
                int(retention),
                100,
            ),
        )
    except Exception:
        keep = 14

    items = sorted(
        BACKUP_ROOT.glob(
            "*.tpbak"
        ),
        key=lambda p:
            p.stat().st_mtime,
        reverse=True,
    )

    for path in items[
        keep:
    ]:
        path.unlink(
            missing_ok=True
        )

        _meta_path(
            path
        ).unlink(
            missing_ok=True
        )


def _load_state() -> dict[str, Any]:

    try:
        value = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(value, dict):
            return value

    except Exception:
        pass

    return {}


def _save_state(
    state: dict[str, Any],
) -> None:

    tmp = Path(
        str(
            STATE_FILE
        ) + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    os.chmod(
        tmp,
        0o600,
    )

    tmp.replace(
        STATE_FILE
    )


def _due_key(
    settings: dict[str, Any],
) -> str | None:

    try:
        zone = ZoneInfo(
            str(
                settings.get(
                    "timezone",
                    "Asia/Tehran",
                )
            )
        )
    except Exception:
        zone = ZoneInfo(
            "Asia/Tehran"
        )

    now = datetime.now(
        zone
    )

    frequency = str(
        settings.get(
            "frequency",
            "daily",
        )
    )

    minute = max(
        0,
        min(
            int(
                settings.get(
                    "minute",
                    0,
                )
            ),
            59,
        ),
    )

    if frequency == "hourly":

        if now.minute < minute:
            return None

        return (
            "hourly:"
            + now.strftime(
                "%Y-%m-%d-%H"
            )
        )

    hour = max(
        0,
        min(
            int(
                settings.get(
                    "hour",
                    3,
                )
            ),
            23,
        ),
    )

    if (
        now.hour,
        now.minute,
    ) < (
        hour,
        minute,
    ):
        return None

    if frequency == "weekly":

        weekday = max(
            0,
            min(
                int(
                    settings.get(
                        "weekday",
                        0,
                    )
                ),
                6,
            ),
        )

        if now.weekday() != weekday:
            return None

        year, week, _ = (
            now.isocalendar()
        )

        return (
            f"weekly:{year}-{week}"
        )

    return (
        "daily:"
        + now.strftime(
            "%Y-%m-%d"
        )
    )


def run_auto_backup_if_due() -> dict[
    str,
    Any,
]:

    ensure_backup_environment()

    settings = (
        load_settings()
    )

    if not settings.get(
        "enabled"
    ):
        return {
            "ok": True,
            "ran": False,
            "reason": "disabled",
        }

    key = _due_key(
        settings
    )

    if key is None:
        return {
            "ok": True,
            "ran": False,
            "reason": "not_due",
        }

    state = _load_state()

    if state.get(
        "last_auto_key"
    ) == key:

        return {
            "ok": True,
            "ran": False,
            "reason":
                "already_done",
        }

    result = create_backup(
        kind="auto",
        send_telegram=bool(
            settings.get(
                "send_telegram"
            )
        ),
        telegram_chat_id=str(
            settings.get(
                "telegram_chat_id"
            ) or ""
        ),
    )

    state[
        "last_auto_key"
    ] = key

    state[
        "last_auto_at"
    ] = _iso_now()

    state[
        "last_auto_filename"
    ] = result[
        "filename"
    ]

    _save_state(
        state
    )

    cleanup_retention(
        int(
            settings.get(
                "retention",
                14,
            )
        )
    )

    return {
        "ok": True,
        "ran": True,
        "backup": result,
    }


ensure_backup_environment()
