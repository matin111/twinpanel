from __future__ import annotations

import io
import math
import re
import tarfile
import zipfile
from datetime import datetime, timezone
from typing import Any


EYLAN_SOURCE = "eylan"
EXPECTED_SQL_SUFFIX = "root/instance/postgres_dump.sql"
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_SQL_BYTES = 768 * 1024 * 1024

_COPY_RE = re.compile(
    r'^COPY\s+public\."?user"?\s*\((?P<columns>[^)]*)\)\s+FROM\s+stdin;$',
    re.IGNORECASE,
)


def _safe_member_name(name: str) -> str:
    return str(name or "").replace("\\", "/").lstrip("./")


def _is_expected_sql(name: str) -> bool:
    normalized = _safe_member_name(name)
    return normalized == EXPECTED_SQL_SUFFIX or normalized.endswith("/" + EXPECTED_SQL_SUFFIX)


def _read_archive_member(raw: bytes, filename: str) -> bytes:
    if not raw:
        raise ValueError("Eylan backup is empty")
    if len(raw) > MAX_ARCHIVE_BYTES:
        raise ValueError("Eylan backup is larger than the supported upload limit")

    lower_name = str(filename or "").lower()

    if lower_name.endswith((".tar.gz", ".tgz", ".tar")):
        try:
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as archive:
                matches = []
                for member in archive.getmembers():
                    if not member.isfile():
                        continue
                    if member.issym() or member.islnk():
                        continue
                    if _is_expected_sql(member.name):
                        matches.append(member)
                if len(matches) != 1:
                    raise ValueError("Eylan backup must contain exactly one root/instance/postgres_dump.sql")
                member = matches[0]
                if member.size < 0 or member.size > MAX_SQL_BYTES:
                    raise ValueError("Eylan postgres_dump.sql is larger than the supported limit")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError("Unable to read Eylan postgres_dump.sql")
                data = stream.read(MAX_SQL_BYTES + 1)
        except (tarfile.TarError, OSError) as exc:
            raise ValueError("Invalid Eylan tar backup") from exc
    elif lower_name.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                matches = []
                for info in archive.infolist():
                    if info.is_dir() or not _is_expected_sql(info.filename):
                        continue
                    normalized = _safe_member_name(info.filename)
                    if any(part == ".." for part in normalized.split("/")):
                        continue
                    matches.append(info)
                if len(matches) != 1:
                    raise ValueError("Eylan backup must contain exactly one root/instance/postgres_dump.sql")
                info = matches[0]
                if info.file_size < 0 or info.file_size > MAX_SQL_BYTES:
                    raise ValueError("Eylan postgres_dump.sql is larger than the supported limit")
                with archive.open(info, "r") as stream:
                    data = stream.read(MAX_SQL_BYTES + 1)
        except (zipfile.BadZipFile, OSError) as exc:
            raise ValueError("Invalid Eylan zip backup") from exc
    else:
        raise ValueError("Eylan backup must be .tar.gz, .tgz, .tar or .zip")

    if len(data) > MAX_SQL_BYTES:
        raise ValueError("Eylan postgres_dump.sql is larger than the supported limit")
    return data


def _copy_unescape(value: str) -> str | None:
    if value == r"\N":
        return None
    output: list[str] = []
    index = 0
    escapes = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\"}
    while index < len(value):
        char = value[index]
        if char != "\\" or index + 1 >= len(value):
            output.append(char)
            index += 1
            continue
        nxt = value[index + 1]
        if nxt in escapes:
            output.append(escapes[nxt])
            index += 2
            continue
        if nxt.isdigit():
            digits = value[index + 1 : index + 4]
            octal = ""
            for digit in digits:
                if digit not in "01234567":
                    break
                octal += digit
            if octal:
                output.append(chr(int(octal, 8)))
                index += 1 + len(octal)
                continue
        output.append(nxt)
        index += 2
    return "".join(output)


def _int_value(value: Any, *, field: str, default: int = 0) -> int:
    if value is None or str(value).strip() == "":
        return default
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid Eylan {field}") from exc
    if parsed < 0:
        raise ValueError(f"Eylan {field} must be non-negative")
    return parsed


def _traffic_limit_bytes(data_limit: Any, data_limit_unit: Any) -> int:
    value = _int_value(data_limit, field="data_limit", default=0)
    if value == 0:
        return 0
    unit = str(data_limit_unit or "").strip().upper().replace("IB", "B")
    factors = {
        "B": 1,
        "BYTE": 1,
        "BYTES": 1,
        "KB": 1024,
        "MB": 1024**2,
        "GB": 1024**3,
        "TB": 1024**4,
    }
    if unit not in factors:
        raise ValueError(f"unsupported Eylan data_limit_unit: {data_limit_unit}")
    return value * factors[unit]


def _expiry_iso(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"invalid Eylan expiry_date: {raw}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat().replace("+00:00", "Z")


def _password(row: dict[str, Any]) -> str | None:
    for key in ("cisco_password", "l2tp_password"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return None


def parse_eylan_sql(sql_bytes: bytes) -> list[dict[str, Any]]:
    try:
        text = sql_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Eylan postgres_dump.sql must be UTF-8 text") from exc

    lines = iter(text.splitlines())
    columns: list[str] | None = None
    rows: list[dict[str, Any]] = []

    for line in lines:
        match = _COPY_RE.match(line.strip())
        if not match:
            continue
        columns = [part.strip().strip('"') for part in match.group("columns").split(",")]
        required = {
            "id",
            "username",
            "expiry_date",
            "data_limit",
            "data_limit_unit",
            "download_bytes",
            "upload_bytes",
            "l2tp_password",
            "cisco_password",
        }
        missing = sorted(required.difference(columns))
        if missing:
            raise ValueError("Eylan user COPY block is missing columns: " + ", ".join(missing))

        for data_line in lines:
            if data_line == r"\.":
                break
            values = data_line.split("\t")
            if len(values) != len(columns):
                raise ValueError("Eylan user COPY row does not match its column count")
            source = {column: _copy_unescape(value) for column, value in zip(columns, values, strict=True)}
            username = str(source.get("username") or "").strip()
            source_id = str(source.get("id") or username).strip()
            if not username or not source_id:
                continue
            password = _password(source)
            download = _int_value(source.get("download_bytes"), field="download_bytes")
            upload = _int_value(source.get("upload_bytes"), field="upload_bytes")
            warnings: list[str] = []
            if not password:
                warnings.append("missing_password")
            try:
                limit_bytes = _traffic_limit_bytes(source.get("data_limit"), source.get("data_limit_unit"))
            except ValueError as exc:
                warnings.append(str(exc))
                limit_bytes = 0
            try:
                expires_at = _expiry_iso(source.get("expiry_date"))
            except ValueError as exc:
                warnings.append(str(exc))
                expires_at = None

            rows.append(
                {
                    "index": len(rows),
                    "source": EYLAN_SOURCE,
                    "source_id": source_id,
                    "username": username,
                    "password": password,
                    "traffic_limit_bytes": limit_bytes,
                    "traffic_used_bytes": download + upload,
                    "expires_at": expires_at,
                    "ready_for_future_import": not warnings,
                    "warnings": warnings,
                }
            )
        break

    if columns is None:
        raise ValueError('Eylan postgres_dump.sql does not contain COPY public."user"')
    if not rows:
        raise ValueError("Eylan user COPY block contains no importable accounts")
    return rows


def preview_eylan_backup(raw: bytes, filename: str) -> dict[str, Any]:
    sql = _read_archive_member(raw, filename)
    rows = parse_eylan_sql(sql)
    ready = sum(1 for row in rows if row["ready_for_future_import"])
    warnings = sum(1 for row in rows if row["warnings"])
    return {
        "dry_run": True,
        "writes_performed": False,
        "source": EYLAN_SOURCE,
        "summary": {
            "input_records": len(rows),
            "expanded_records": len(rows),
            "ready_records": ready,
            "warning_records": warnings,
        },
        "records": rows,
    }


def duration_days_for_expiry(expires_at: datetime | None, *, now: datetime | None = None) -> int:
    if expires_at is None:
        return 3650
    expiry = expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    else:
        expiry = expiry.astimezone(timezone.utc)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    remaining = (expiry - current).total_seconds()
    return max(1, min(3650, math.ceil(remaining / 86400)))
