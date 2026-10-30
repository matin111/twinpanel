from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "app" / "services" / "migration_center_v1.py"
ROUTER_PATH = ROOT / "app" / "routers" / "migration_center_v1.py"
AGGREGATE_PATH = ROOT / "app" / "routers" / "subscription_admin_v2.py"

spec = importlib.util.spec_from_file_location("migration_center_v1", SERVICE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_marzban_preserves_existing_material() -> None:
    url = "https://legacy.example/sub/alice"
    links = ["vless://existing-client-material"]
    report = module.dry_run_migration(
        "marzban",
        [{"username": "alice", "subscription_url": url, "links": links}],
    )
    row = report["records"][0]
    assert report["dry_run"] is True
    assert report["writes_performed"] is False
    assert row["legacy_subscription_url"] == url
    assert row["credentials"]["links"] == links
    assert row["ready_for_future_import"] is True


def test_marzban_preserves_quota_usage_and_expiry() -> None:
    report = module.dry_run_migration(
        "marzban",
        [
            {
                "username": "alice-state",
                "password": "existing-secret",
                "data_limit": 50_000_000_000,
                "used_traffic": 12_345_678,
                "expire": 1_767_225_600,
            }
        ],
    )
    row = report["records"][0]
    assert row["traffic_limit_bytes"] == 50_000_000_000
    assert row["traffic_used_bytes"] == 12_345_678
    assert row["expires_at"] == "2026-01-01T00:00:00Z"


def test_sanaei_expands_clients_and_preserves_uuid() -> None:
    client_uuid = "11111111-2222-3333-4444-555555555555"
    legacy_url = "https://legacy.example/s/sanaei-client"
    settings = json.dumps(
        {
            "clients": [
                {
                    "id": client_uuid,
                    "email": "sanaei-client",
                    "sub_url": legacy_url,
                }
            ]
        }
    )
    report = module.dry_run_migration(
        "sanaei",
        [{"id": 77, "remark": "existing-inbound", "settings": settings}],
    )
    assert report["summary"]["input_records"] == 1
    assert report["summary"]["expanded_records"] == 1
    row = report["records"][0]
    assert row["credentials"]["uuid"] == client_uuid
    assert row["legacy_subscription_url"] == legacy_url
    assert row["username"] == "sanaei-client"


def test_sanaei_matches_client_stats_and_preserves_account_state() -> None:
    client_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    settings = json.dumps(
        {
            "clients": [
                {
                    "id": client_uuid,
                    "email": "sanaei-state",
                    "totalGB": 25_000_000_000,
                    "expiryTime": 1_767_225_600_000,
                }
            ]
        }
    )
    report = module.dry_run_migration(
        "sanaei",
        [
            {
                "id": 88,
                "settings": settings,
                "clientStats": [
                    {"email": "sanaei-state", "up": 2_000_000, "down": 7_000_000}
                ],
            }
        ],
    )
    row = report["records"][0]
    assert row["traffic_limit_bytes"] == 25_000_000_000
    assert row["traffic_used_bytes"] == 9_000_000
    assert row["expires_at"] == "2026-01-01T00:00:00Z"


def test_zero_state_is_not_confused_with_missing_state() -> None:
    zero_report = module.dry_run_migration(
        "sanaei",
        [
            {
                "id": "bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
                "email": "zero-state",
                "totalGB": 0,
                "up": 0,
                "down": 0,
                "expiryTime": 0,
            }
        ],
    )
    zero = zero_report["records"][0]
    assert "traffic_limit_bytes" in zero and zero["traffic_limit_bytes"] == 0
    assert "traffic_used_bytes" in zero and zero["traffic_used_bytes"] == 0
    assert "expires_at" in zero and zero["expires_at"] is None

    missing_report = module.dry_run_migration(
        "sanaei",
        [{"id": "cccccccc-dddd-eeee-ffff-000000000000", "email": "missing-state"}],
    )
    missing = missing_report["records"][0]
    assert "traffic_limit_bytes" not in missing
    assert "traffic_used_bytes" not in missing
    assert "expires_at" not in missing


def test_normalized_state_survives_phase_two_round_trip() -> None:
    original = module.dry_run_migration(
        "marzban",
        [
            {
                "username": "round-trip",
                "password": "existing-secret",
                "data_limit": 0,
                "used_traffic": 987,
                "expire": 0,
            }
        ],
    )["records"][0]
    normalized_again = module.normalize_record("marzban", original, 0)
    assert normalized_again["traffic_limit_bytes"] == 0
    assert normalized_again["traffic_used_bytes"] == 987
    assert "expires_at" in normalized_again and normalized_again["expires_at"] is None


def test_pasargad_preserves_password_and_url() -> None:
    report = module.dry_run_migration(
        "pasargad",
        [
            {
                "username": "legacy-user",
                "password": "existing-secret",
                "subscription_url": "https://legacy.example/p/legacy-user",
            }
        ],
    )
    row = report["records"][0]
    assert row["credentials"]["password"] == "existing-secret"
    assert row["preservation"]["credentials"] == "preserve_existing"
    assert row["preservation"]["subscription_url"] == "preserve_existing"


def test_missing_legacy_url_warns_without_blocking_import() -> None:
    report = module.dry_run_migration(
        "sanaei",
        [{"id": "11111111-2222-3333-4444-555555555555", "email": "ready-user"}],
    )
    row = report["records"][0]
    assert row["ready_for_future_import"] is True
    assert "missing_legacy_subscription_url" in row["warnings"]
    assert report["summary"]["ready_records"] == 1
    assert report["summary"]["warning_records"] == 1


def test_negative_sanaei_expiry_is_not_guessed() -> None:
    report = module.dry_run_migration(
        "sanaei",
        [
            {
                "id": "dddddddd-eeee-ffff-0000-111111111111",
                "email": "first-use-unknown",
                "expiryTime": -86_400_000,
            }
        ],
    )
    row = report["records"][0]
    assert "expires_at" not in row
    assert "unsupported_negative_expiryTime" in row["warnings"]


def test_missing_required_material_still_blocks_import() -> None:
    report = module.dry_run_migration("pasargad", [{"username": "incomplete"}])
    row = report["records"][0]
    assert row["ready_for_future_import"] is False
    assert "missing_existing_credentials" in row["warnings"]
    assert "missing_legacy_subscription_url" in row["warnings"]
    assert row["credentials"] == {}


def test_missing_source_id_blocks_import() -> None:
    report = module.dry_run_migration(
        "pasargad",
        [{"password": "existing-secret", "subscription_url": "https://legacy.example/sub/no-id"}],
    )
    row = report["records"][0]
    assert row["ready_for_future_import"] is False
    assert "missing_source_id" in row["warnings"]
    assert "missing_username" in row["warnings"]


def test_unsupported_source_is_rejected() -> None:
    try:
        module.dry_run_migration("unknown", [])
    except ValueError as exc:
        assert "unsupported migration source" in str(exc)
    else:
        raise AssertionError("unsupported source must fail closed")


def test_admin_only_route_is_registered_without_main_rewrite() -> None:
    router_source = ROUTER_PATH.read_text(encoding="utf-8")
    aggregate_source = AGGREGATE_PATH.read_text(encoding="utf-8")
    assert 'prefix="/admin/migration-center"' in router_source
    assert "dependencies=[Depends(require_admin)]" in router_source
    assert "migration_center_v1_router.routes" in aggregate_source
    assert 'prefix="/v1"' not in router_source


def test_phase_one_has_no_db_or_mutating_runtime_dependency() -> None:
    service_source = SERVICE_PATH.read_text(encoding="utf-8")
    router_source = ROUTER_PATH.read_text(encoding="utf-8")
    forbidden = (
        "from ..database",
        "from sqlalchemy",
        "get_db(",
        "db.add(",
        "db.commit(",
        "provision.router",
        "ProtocolCredential(",
        "create_subscription_core(",
    )
    for token in forbidden:
        assert token not in service_source
        assert token not in router_source


if __name__ == "__main__":
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
    print(f"migration_center_v1_smoke: {len(tests)} passed")
