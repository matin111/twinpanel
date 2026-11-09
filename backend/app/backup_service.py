from __future__ import annotations

# TWINPANEL_SELECTIVE_BACKUP_SERVICE_V1

import base64
import enum
import gzip
import zipfile
import tempfile
import shutil
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
from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.pool import NullPool

from .backup_telegram_credentials import load_backup_telegram_bot_token as load_bot_token
from .config import settings
from .database import engine


BACKUP_FORMAT = "twinpanel-portable-data-v3"

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

    # Persistent extensions required for a full migration / restore.
    "dns_emergency_iran_settings",
    "dns_emergency_settings",
    "download_assets",
    "main_trial_settings",
    "masterdnsvpn_settings",
    "migration_import_records",
    "modern_protocol_settings",
    "plan_category_assignments",
    "plan_nodes",
    "plan_protocols",
    "plan_trial_settings",
    "reseller_bot_plans",
    "reseller_pool_suspensions",
    "reseller_trial_settings",
    "storefront_settings",
    "subscription_delivery_policy_state",
    "subscription_node_delivery_modes",
    "subscription_runtime_overrides",
    "telegram_imported_accounts",
    "tunnel_transports",
    "vpnshop_runtime_settings",
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
    # Disposable runtime queues / audit / telemetry and dedupe claims.
    "cleanup_jobs",
    "fast_provision_jobs_v1",
    "main_trial_claims",
    "node_backfill_jobs_v1",
    "node_install_progress_v1",
    "node_protocol_applied_endpoints_v1",
    "node_telemetry",
    "quota_audit_logs",
    "reseller_trial_claims",
    "subscription_expiry_notification_claims",
    "trial_claims",
    "twinpanel_selected_tunnel_jobs_v1",
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

    if type_name == "account_credential_rewrap_v2":
        # Encrypted credential fields are compressed as their original JSON
        # while inside the OUTER backup. On restore, encrypt again
        # using the destination panel's APP_SECRET_KEY, so migration does not
        # require copying the old deployment .env or database credentials.
        from .routers import account_delivery as account_crypto
        return account_crypto._enc(_unpack(value["payload"]))

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
        for key, item in value.items()
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


# Only irreplaceable, administrator-created settings and cryptographic
# identities are archived. Never recursively archive /etc/twinpanel:
# it contains thousands of generated sing-box snapshots and runtime files.
# Runtime configuration and node software must be recreated by the installer
# and the centralized provisioning controller.
PERSISTENT_CONFIG_FILES = frozenset({
    "/etc/twinpanel-telegram-api.env",
    "/etc/twinpanel/backup-telegram-bot.json",
    "/etc/twinpanel/backup-telegram-token.enc",
    "/etc/twinpanel/backup-telegram.key",
    "/etc/twinpanel/masterdnsvpn/encrypt_key.txt",
    "/etc/twinpanel/masterdnsvpn/server_config.toml",
    "/etc/twinpanel/controller-ip/ca.crt",
    "/etc/twinpanel/controller-ip/ca.key",
    "/etc/twinpanel/sing-box/managed-ca.crt",
    "/etc/twinpanel/sing-box/managed-ca.key",
    "/etc/twinpanel/sing-box/server.crt",
    "/etc/twinpanel/sing-box/server.key",
    "/etc/twinpanel/standalone/amneziawg/private.key",
})


def _collect_admin_files(
    node_key_paths: set[str],
) -> dict[str, Any]:
    # Credential and CA material that cannot safely be reconstructed for
    # already-enrolled nodes are exceptions to the data-only backup policy.
    # A legacy backup key is excluded from the portable data archive.
    allowed = set(PERSISTENT_CONFIG_FILES)
    for raw in node_key_paths:
        if not raw:
            continue
        path = Path(raw)
        if (
            not path.is_absolute()
            or ".." in path.parts
            or path == BACKUP_KEY
        ):
            continue
        # Only the explicit SSH key files referenced by node_access;
        # never back up whole home directories or runtime trees.
        allowed.add(str(path))

    result: dict[str, Any] = {}
    for name in sorted(allowed):
        path = Path(name)
        if path == BACKUP_KEY:
            continue
        entry = _file_entry(path)
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
        # Every table must reflect the same committed database snapshot.
        # Without this, a busy panel may export subscriptions and wallets
        # from different moments even though each individual SELECT succeeds.
        conn.execute(text(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
        ))

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

                if name == "protocol_credentials":
                    # The source rows contain per-user Fernet ciphertext.
                    # Ciphertext is deliberately incompressible; rewrap only
                    # the JSON that we can authenticate and decrypt locally.
                    # WARNING: portable v3 backups include these sensitive
                    # credentials; limit access to the resulting archive.
                    from .routers import account_delivery as account_crypto
                    for field in ("secret_encrypted", "config_text_encrypted"):
                        ciphertext = plain.get(field)
                        if not isinstance(ciphertext, str) or not ciphertext:
                            continue
                        decoded = account_crypto._dec(ciphertext)
                        if decoded is None:
                            # Preserve unreadable/legacy values byte-for-byte.
                            # Never silently erase a credential.
                            continue
                        plain[field] = {
                            "__tp_type__": "account_credential_rewrap_v2",
                            "payload": decoded,
                        }

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
        "version": 3,
        "scope": "persistent-panel-data",
        "credential_encoding": "account_credential_rewrap_v2",
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

    # Portable, keyless gzip archive. The file contains sensitive secrets:
    # restrict access and transfer only over protected channels.
    archive_bytes = compressed

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
        archive_bytes
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
        "sha256": hashlib.sha256(archive_bytes).hexdigest(),
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

    # Keep the archive until Telegram verifies every part and final checksum.
    # Failed or incomplete transfers remain available for a retry.
    if send_telegram and meta.get("telegram_sent"):
        _remove_uploaded_archive(target)
        meta = _read_meta(target)

    return meta


def _remove_uploaded_archive(path: Path) -> bool:
    meta = _read_meta(path)
    if not meta.get("telegram_sent") or not meta.get("telegram_parts_total"):
        return False
    expected = set(range(1, int(meta["telegram_parts_total"]) + 1))
    if not expected.issubset(set(meta.get("telegram_parts_sent") or [])):
        return False
    path.unlink(missing_ok=True)
    meta["archive_on_server"] = False
    meta["telegram_only"] = True
    _write_meta(path, meta)
    return True


def list_backups() -> list[
    dict[str, Any]
]:

    ensure_backup_environment()

    result = []

    # Show successful Telegram-only backups even after encrypted local
    # archives are removed. Metadata contains no private backup content.
    archived_names: set[str] = set()
    for meta_file in BACKUP_ROOT.glob("*.tpbak.meta.json"):
        try:
            meta = json.loads(meta_file.read_text())
            name = str(meta.get("filename") or "")
            if not name.endswith(".tpbak"):
                continue
            local = BACKUP_ROOT / name
            if not local.is_file() and meta.get("telegram_sent"):
                meta["archive_on_server"] = False
                meta["telegram_only"] = True
                result.append(meta)
                archived_names.add(name)
        except Exception:
            continue

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

        meta["archive_on_server"] = True
        result.append(
            meta
        )

    return sorted(
        result,
        key=lambda item: str(item.get("created_at") or ""),
        reverse=True,
    )


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


def delete_backup(filename: str) -> None:
    safe=Path(filename).name
    if safe!=filename or not safe.endswith(".tpbak"):
        raise ValueError("Invalid backup filename")
    path=BACKUP_ROOT/safe
    meta=_meta_path(path)
    # For Telegram-only files this deletes the local audit record only.
    if not path.exists() and not meta.exists():
        raise FileNotFoundError(safe)
    path.unlink(missing_ok=True)
    meta.unlink(missing_ok=True)


def _decode_backup(
    path: Path,
) -> dict[str, Any]:

    # The v3 archive is a portable gzip stream; legacy backup archives
    # are deliberately unsupported by the new restore flow.
    compressed = path.read_bytes()
    if not compressed.startswith(b"\x1f\x8b"):
        raise ValueError("UNSUPPORTED_BACKUP_FORMAT_V3_ONLY")

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

    # One uploaded ZIP contains exactly one existing portable .tpbak.
    # Do not extract arbitrary archive paths or unbounded ZIP entries.
    if original_name.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(source, "r") as archive:
                files = [item for item in archive.infolist() if not item.is_dir()]
                if (len(files) != 1
                    or files[0].filename != Path(files[0].filename).name
                    or not files[0].filename.endswith(".tpbak")
                    or files[0].file_size > 1024 * 1024 * 1024):
                    raise ValueError("ZIP_MUST_CONTAIN_ONE_TPBAK")
                with tempfile.NamedTemporaryFile(
                    mode="wb", suffix=".tpbak", prefix=".zip-import-",
                    dir=BACKUP_ROOT, delete=False,
                ) as output:
                    staged = Path(output.name)
                    os.chmod(staged, 0o600)
                    try:
                        with archive.open(files[0]) as incoming:
                            total = 0
                            while True:
                                chunk = incoming.read(1024 * 1024)
                                if not chunk:
                                    break
                                total += len(chunk)
                                if total > 1024 * 1024 * 1024:
                                    raise ValueError("ZIP_MEMBER_TOO_LARGE")
                                output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                    except BaseException:
                        staged.unlink(missing_ok=True)
                        raise
                try:
                    return import_backup_file(staged, files[0].filename)
                finally:
                    staged.unlink(missing_ok=True)
        except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            raise ValueError("BACKUP_ZIP_INVALID") from exc

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

    # Avoid reading a large backup into RAM a second time during import.
    # inspect_backup() has already validated the portable archive format.
    # Stream to a private, fsynced temporary file and rename atomically.
    import shutil
    with tempfile.NamedTemporaryFile(
        mode="wb", prefix=".tpbak-import-",
        suffix=".tmp", dir=BACKUP_ROOT, delete=False,
    ) as out:
        staged = Path(out.name)
        os.chmod(staged, 0o600)
        try:
            with source.open("rb") as incoming:
                shutil.copyfileobj(incoming, out, length=1024 * 1024)
            out.flush()
            os.fsync(out.fileno())
        except BaseException:
            staged.unlink(missing_ok=True)
            raise
    try:
        staged.replace(target)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise

    with target.open("rb") as checksum_source:
        copied_sha256 = hashlib.file_digest(
            checksum_source, "sha256"
        ).hexdigest()

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
        "sha256": copied_sha256,
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

    # After the dedicated backup bot has been migrated off the cloud API,
    # every interaction with that bot (probe, receipt, completion message)
    # must use the same local Bot API server. Never accidentally send it back
    # to the logged-out Telegram cloud Bot API.
    from .backup_telegram_single_file_v1 import local_api_url
    backup_api = local_api_url()
    base_url = backup_api or "https://api.telegram.org"
    try:
        response = httpx.post(
            f"{base_url}/bot{token}/{method}",
            data=data or {},
            files=files,
            timeout=timeout,
            trust_env=not bool(backup_api),
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



# Keep each Telegram document well below the 50 MB Bot API upload limit.
# Keyless v3 archives contain sensitive data; restrict Telegram destination.
TELEGRAM_BACKUP_PART_BYTES = 40 * 1024 * 1024


def send_backup_to_telegram(
    backup_path: Path,
    chat_id: str,
) -> dict[str, Any]:
    import math
    import tempfile

    token = load_bot_token()
    meta = _read_meta(backup_path)
    # When a local Telegram Bot API server is explicitly configured, send
    # the complete backup archive as ONE document (up to 2GB).
    # Leave cloud-API multipart as the non-destructive fallback for existing
    # installations which cannot send files larger than 50MB.
    from .backup_telegram_single_file_v1 import send_single_backup
    try:
        result = send_single_backup(
            backup_path, chat_id, token=token, meta=meta,
            write_meta=_write_meta,
        )
    except Exception as exc:
        meta["telegram_error"] = (
            str(exc)[:250] if str(exc).startswith("BACKUP_")
            else "BACKUP_SINGLE_FILE_DELIVERY_FAILED"
        )
        _write_meta(backup_path, meta)
        raise
    if result is not None:
        return result

    file_size = backup_path.stat().st_size
    parts = max(1, math.ceil(file_size / TELEGRAM_BACKUP_PART_BYTES))
    # Do not silently resume delivery to a different chat.
    already_sent = meta.get("telegram_parts_sent") or []
    if meta.get("telegram_delivery_chat") != str(chat_id):
        already_sent = []
    if not isinstance(already_sent, list):
        already_sent = []
    already_sent = [
        int(i) for i in already_sent
        if isinstance(i, int) and 1 <= i <= parts
    ]
    completed = set(already_sent)
    meta["telegram_delivery_chat"] = str(chat_id)
    meta["telegram_parts_total"] = parts
    meta["telegram_parts_sent"] = sorted(completed)
    meta["telegram_sent"] = False
    _write_meta(backup_path, meta)

    caption_header = (
        "TwinPanel backup\\n"
        f"Type: {meta.get('kind', 'backup')}\\n"
        f"Created: {meta.get('created_at','')}\\n"
    )
    with backup_path.open("rb") as source:
        for idx in range(1, parts + 1):
            if idx in completed:
                continue
            # One part at a time, bounded memory and disk use; no large
            # in-memory read and no retained duplicate backup files.
            source.seek((idx - 1) * TELEGRAM_BACKUP_PART_BYTES)
            with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as spool:
                remaining = min(
                    TELEGRAM_BACKUP_PART_BYTES,
                    file_size - ((idx - 1) * TELEGRAM_BACKUP_PART_BYTES),
                )
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise RuntimeError("BACKUP_SOURCE_TRUNCATED")
                    spool.write(chunk)
                    remaining -= len(chunk)
                spool.seek(0)
                filename = (
                    backup_path.name if parts == 1 else
                    f"{backup_path.name}.part{idx:03d}of{parts:03d}"
                )
                try:
                    _telegram_api_call(
                        token, "sendDocument",
                        data={
                            "chat_id": str(chat_id),
                            "caption": (
                                caption_header
                                + f"Part {idx}/{parts}. Reassemble in numeric order."
                            ),
                        },
                        files={
                            "document": (
                                filename, spool, "application/octet-stream",
                            ),
                        },
                        timeout=240.0,
                    )
                except Exception as exc:
                    meta["telegram_error"] = str(exc)[:500]
                    meta["telegram_parts_sent"] = sorted(completed)
                    _write_meta(backup_path, meta)
                    raise
            completed.add(idx)
            meta["telegram_parts_sent"] = sorted(completed)
            meta["telegram_error"] = None
            _write_meta(backup_path, meta)

    # A checksum sent separately allows verification after joining parts.
    # Send checksum for portable archive integrity verification.
    try:
        _telegram_api_call(
            token, "sendMessage",
            data={
                "chat_id": str(chat_id),
                "text": (
                    f"TwinPanel backup delivery complete: {backup_path.name}\\n"
                    f"Parts: {parts} (join in ascending order).\\n"
                    f"SHA256: {meta.get('sha256','')}\\n"
                    "After joining, verify SHA256 before restoring. "
                    "Store this sensitive archive in a private location."
                ),
            },
            timeout=30.0,
        )
    except Exception as exc:
        meta["telegram_error"] = str(exc)[:500]
        _write_meta(backup_path, meta)
        raise

    meta["telegram_sent"] = True
    meta["telegram_sent_at"] = _iso_now()
    meta["telegram_error"] = None
    _write_meta(backup_path, meta)
    return {
        "ok": True,
        "chat_id": str(chat_id),
        "parts": parts,
        "parts_sent": len(completed),
        "sha256": meta.get("sha256"),
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

    # Validate backup compatibility and affected dependent tables BEFORE
    # creating a large temporary safety archive or changing any live rows.
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

    # Fail closed BEFORE any TRUNCATE. Older incomplete archives must not
    # erase persistent tables introduced by a newer panel release.
    required = set(_current_tables())
    missing = required - set(payload["tables"])
    if missing:
        raise RuntimeError(
            "BACKUP_INCOMPLETE_FOR_CURRENT_SCHEMA: " +
            ",".join(sorted(missing))
        )
    # CASCADE also clears tables not explicitly named in TRUNCATE.
    # Reject restoring into an occupied instance when any dependent table
    # outside the archive contains rows. Restoration must be rehearsed
    # on an isolated DB, not used as a live destructive merge.
    with engine.connect() as preflight:
        affected = preflight.execute(text("""
            SELECT DISTINCT child.relname
            FROM pg_constraint fk
            JOIN pg_class child ON child.oid=fk.conrelid
            JOIN pg_class parent ON parent.oid=fk.confrelid
            JOIN pg_namespace ns ON ns.oid=child.relnamespace
            WHERE fk.contype='f' AND ns.nspname='public'
              AND parent.relname = ANY(:parents)
              AND child.relname <> ALL(:included)
        """), {
            "parents": restore_names,
            "included": restore_names,
        }).scalars().all()
        nonempty=[]
        for name in affected:
            quoted_name = '"' + name.replace('"','""') + '"'
            if preflight.execute(
                text("SELECT EXISTS(SELECT 1 FROM "+quoted_name+" LIMIT 1)")
            ).scalar():
                nonempty.append(name)
        if nonempty:
            raise RuntimeError(
                "RESTORE_WOULD_ERASE_EXCLUDED_TABLES: " +
                ",".join(sorted(nonempty))
            )

    # A private local safety copy is mandatory before any destructive restore.
    # A new installation must be restorable without configuring Telegram.
    safety = create_backup(kind="pre-restore", send_telegram=False)
    if not (BACKUP_ROOT / safety["filename"]).is_file():
        raise RuntimeError("RESTORE_SAFETY_ARCHIVE_MISSING")

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

    for path in items[keep:]:
        # Never prune the only available copy following an upload failure.
        # Backup retention must not destroy unconfirmed backup archives.
        if not _read_meta(path).get("telegram_sent"):
            continue
        _remove_uploaded_archive(path)


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


# Drain older updater snapshots gradually, only after the updater is done.
# Never delete a backup that has not been fully delivered and checksum-verified.
def _forward_one_retained_archive(settings: dict[str, Any]) -> dict[str, Any] | None:
    if not settings.get("send_telegram"):
        return None
    chat_id = str(settings.get("telegram_chat_id") or "").strip()
    if not chat_id:
        return None
    import subprocess
    if subprocess.run(
        ["/usr/bin/systemctl","is-active","--quiet","twinpanel-updater.service"],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False,
        timeout=5,
    ).returncode == 0:
        return {"ok":True,"ran":False,"reason":"updater_in_progress"}

    from datetime import timedelta
    progress_file = BACKUP_ROOT/"pending-telegram-delivery-state.json"
    try:
        state = json.loads(progress_file.read_text())
    except Exception:
        state = {}
    now = _now_utc()
    try:
        previous = datetime.fromisoformat(str(state.get("last_attempt") or ""))
        if now - previous < timedelta(minutes=25):
            return None
    except (ValueError,TypeError):
        pass

    files = sorted(
        BACKUP_ROOT.glob("*.tpbak"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    for path in files:
        meta = _read_meta(path)
        if meta.get("telegram_sent"):
            _remove_uploaded_archive(path)
            continue
        if not meta or meta.get("kind") not in {
            "pre_update","pre-restore","auto","manual",
        }:
            continue
        # Limit to one archive per timer tick, with a durable throttle.
        progress_file.write_text(json.dumps({
            "last_attempt":now.isoformat(),"filename":path.name,
        }))
        os.chmod(progress_file,0o600)
        try:
            if (
                meta.get("size_bytes") != path.stat().st_size
                or not meta.get("sha256")
            ):
                raise ValueError("BACKUP_SIZE_OR_HASH_METADATA_MISSING")
            with path.open("rb") as handle:
                checksum = hashlib.file_digest(handle, "sha256").hexdigest()
            if checksum != meta["sha256"]:
                raise ValueError("BACKUP_HASH_MISMATCH")
            send_backup_to_telegram(path,chat_id)
            if not _remove_uploaded_archive(path):
                raise RuntimeError("BACKUP_DELIVERY_UNCONFIRMED")
            return {"ok":True,"ran":False,"reason":"older_backup_delivered",
                    "filename":path.name}
        except Exception as exc:
            meta = _read_meta(path)
            meta["telegram_error"] = (
                str(exc)[:180] if isinstance(exc, ValueError)
                else type(exc).__name__
            )
            _write_meta(path,meta)
            return {"ok":False,"ran":False,
                    "reason":"older_backup_delivery_retry_pending",
                    "filename":path.name,
                    "error_code":type(exc).__name__}
    return None


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
        # Disabling the schedule must not leave already-created updater
        # safety archives permanently on disk. Drain those gradually.
        return _forward_one_retained_archive(settings) or {
            "ok": True,
            "ran": False,
            "reason": "disabled",
        }

    if not settings.get("send_telegram") or not str(
        settings.get("telegram_chat_id") or ""
    ).strip():
        # Telegram-only backup policy: never create a new unattended
        # archive that would be left permanently on the server.
        return {
            "ok": False,
            "ran": False,
            "reason": "telegram_destination_required",
        }

    key = _due_key(
        settings
    )

    if key is None:
        return _forward_one_retained_archive(settings) or {
            "ok": True, "ran": False, "reason": "not_due",
        }

    state = _load_state()

    if state.get(
        "last_auto_key"
    ) == key:
        # The backup may have been created successfully while Telegram
        # rejected an oversized attachment. Retry delivery of that same
        # backup archive, never create another backup or duplicate parts.
        if settings.get("send_telegram"):
            filename = str(state.get("last_auto_filename") or "")
            chat_id = str(settings.get("telegram_chat_id") or "").strip()
            if filename and chat_id:
                try:
                    safe=Path(filename).name
                    if safe!=filename or not safe.endswith(".tpbak"):
                        raise ValueError("INVALID_BACKUP_FILENAME")
                    path=BACKUP_ROOT/safe
                    meta=_read_meta(path)
                    if meta.get("telegram_sent"):
                        return _forward_one_retained_archive(settings) or {
                            "ok":True,"ran":False,"reason":"already_delivered"
                        }
                    if not path.is_file():
                        raise FileNotFoundError(filename)
                    if not meta.get("telegram_sent"):
                        try:
                            result = send_backup_to_telegram(path, chat_id)
                            _remove_uploaded_archive(path)
                            return {"ok": True, "ran": False,
                                    "reason": "telegram_delivery_recovered",
                                    "telegram": result}
                        except Exception as exc:
                            return {"ok": False, "ran": False,
                                    "reason": "telegram_delivery_retry_pending",
                                    "error": str(exc)[:240]}
                except Exception as exc:
                    return {"ok": False, "ran": False,
                            "reason": "telegram_delivery_backup_missing",
                            "error": type(exc).__name__}
        return _forward_one_retained_archive(settings) or {
            "ok": True,
            "ran": False,
            "reason": "already_done",
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
