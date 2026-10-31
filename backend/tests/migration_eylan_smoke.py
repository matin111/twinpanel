from __future__ import annotations

import importlib.util
import io
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "app" / "services" / "migration_eylan.py"
ROUTER_PATH = ROOT / "app" / "routers" / "migration_center_v2.py"
UI_PATH = ROOT.parent / "components" / "migration-center-admin.tsx"


def _load_service():
    spec = importlib.util.spec_from_file_location("migration_eylan_under_test", SERVICE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sql(*rows: str) -> bytes:
    columns = (
        'id, username, expiry_date, data_limit, data_limit_unit, '
        'download_bytes, upload_bytes, l2tp_password, cisco_password'
    )
    body = "\n".join(rows)
    return f'COPY public."user" ({columns}) FROM stdin;\n{body}\n\\.\n'.encode()


def _zip(sql: bytes, path: str = "root/instance/postgres_dump.sql") -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(path, sql)
    return stream.getvalue()


def _tgz(sql: bytes) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        info = tarfile.TarInfo("root/instance/postgres_dump.sql")
        info.size = len(sql)
        archive.addfile(info, io.BytesIO(sql))
    return stream.getvalue()


def test_parser_uses_download_plus_upload_and_cisco_password() -> None:
    service = _load_service()
    rows = service.parse_eylan_sql(
        _sql("7\talice\t2026-12-01 12:00:00+00\t50\tGB\t1024\t2048\tl2pass\tciscopass")
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["source_id"] == "7"
    assert row["username"] == "alice"
    assert row["password"] == "ciscopass"
    assert row["traffic_limit_bytes"] == 50 * 1024**3
    assert row["traffic_used_bytes"] == 3072
    assert row["expires_at"] == "2026-12-01T12:00:00Z"
    assert row["ready_for_future_import"] is True


def test_parser_accepts_decimal_data_limit_exactly() -> None:
    service = _load_service()
    row = service.parse_eylan_sql(
        _sql("71\tdecimal\t2026-12-01 12:00:00+00\t15.25\tGB\t100\t200\tl2\tcisco")
    )[0]
    assert row["traffic_limit_bytes"] == 15 * 1024**3 + 256 * 1024**2
    assert row["traffic_used_bytes"] == 300
    assert row["warnings"] == []
    assert row["ready_for_future_import"] is True


def test_parser_accepts_integer_shaped_decimal_limit() -> None:
    service = _load_service()
    row = service.parse_eylan_sql(
        _sql("72\tdecimal2\t\\N\t50.00\tGB\t0\t0\tl2\tcisco")
    )[0]
    assert row["traffic_limit_bytes"] == 50 * 1024**3
    assert row["warnings"] == []


def test_parser_falls_back_to_l2tp_password() -> None:
    service = _load_service()
    row = service.parse_eylan_sql(
        _sql("8\tbob\t\\N\t10\tGB\t0\t9\tl2-only\t\\N")
    )[0]
    assert row["password"] == "l2-only"
    assert row["traffic_used_bytes"] == 9
    assert row["expires_at"] is None


def test_missing_password_is_preview_warning_not_silent_generation() -> None:
    service = _load_service()
    row = service.parse_eylan_sql(
        _sql("9\tcarol\t\\N\t1\tGB\t1\t2\t\\N\t\\N")
    )[0]
    assert row["ready_for_future_import"] is False
    assert "missing_password" in row["warnings"]


def test_zip_and_targz_preview_read_only_expected_member() -> None:
    service = _load_service()
    sql = _sql("10\tdave\t2026-11-15 00:00:00+00\t2\tGB\t5\t6\tl2\tcisco")
    for filename, archive in (("backup.zip", _zip(sql)), ("backup.tar.gz", _tgz(sql))):
        result = service.preview_eylan_backup(archive, filename)
        assert result["dry_run"] is True
        assert result["writes_performed"] is False
        assert result["source"] == "eylan"
        assert result["summary"]["ready_records"] == 1


def test_archive_without_expected_sql_is_rejected() -> None:
    service = _load_service()
    try:
        service.preview_eylan_backup(_zip(b"select 1", "other.sql"), "backup.zip")
    except ValueError as exc:
        assert "exactly one root/instance/postgres_dump.sql" in str(exc)
    else:
        raise AssertionError("invalid Eylan archive was accepted")


def test_naive_expiry_is_normalized_before_duration_math() -> None:
    service = _load_service()
    days = service.duration_days_for_expiry(
        datetime(2026, 11, 3, 0, 0, 0),
        now=datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc),
    )
    assert days == 2


def test_router_and_ui_keep_eylan_on_dedicated_safe_path() -> None:
    router = ROUTER_PATH.read_text(encoding="utf-8")
    ui = UI_PATH.read_text(encoding="utf-8")
    assert '@admin_router.post("/eylan/preview")' in router
    assert '@admin_router.post("/eylan/import")' in router
    assert "preview_eylan_backup" in router
    assert "traffic_used_bytes = int(record.traffic_used_bytes)" in router
    assert "subscription_uuids[sub.id] = str(uuid.uuid4())" in router
    assert "await provision_migrated_v2ray_batch(db, subscription_uuids)" in router
    assert 'type Source="sanaei"|"marzban"|"pasargad"|"eylan"' in ui
    assert 'accept=".tar,.tar.gz,.tgz,.zip,application/gzip,application/zip"' in ui
    assert '"/v1/admin/migration-center/eylan/preview"' in ui
    assert '"/v1/admin/migration-center/eylan/import"' in ui
    assert 'item.password?pick("موجود","Set")' in ui


if __name__ == "__main__":
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
    print(f"migration_eylan_smoke: {len(tests)} passed")
