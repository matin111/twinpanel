from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "app" / "services" / "migration_import_v2.py"
BATCH_SERVICE_PATH = ROOT / "app" / "services" / "migration_v2ray_batch.py"
ROUTER_PATH = ROOT / "app" / "routers" / "migration_center_v2.py"
AGGREGATE_PATH = ROOT / "app" / "routers" / "subscription_admin_v2.py"
MODEL_PATH = ROOT / "app" / "migration_import_models.py"
UI_PATH = ROOT.parent / "components" / "migration-center-admin.tsx"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_phase2_has_source_identity_idempotency() -> None:
    source = _text(MODEL_PATH)
    assert 'UniqueConstraint("source", "source_id"' in source
    assert 'UniqueConstraint("legacy_token"' in source
    service = _text(SERVICE_PATH)
    assert "MigrationImportRecord.source == source" in service
    assert "MigrationImportRecord.source_id == source_id" in service
    assert '"idempotent": True' in service


def test_phase2_repairs_existing_subscription_without_duplicate() -> None:
    service = _text(SERVICE_PATH)
    assert "def _repair_existing_subscription(" in service
    assert "sub = db.get(Subscription, marker.subscription_id)" in service
    assert 'raise ValueError("existing migration record belongs to a different TwinPanel user")' in service
    assert "for field, (present, value) in state.items():" in service
    assert '"updated": updated' in service
    existing_block = service.split("if existing:", 1)[1].split("if not normalized.get", 1)[0]
    assert "Subscription(" not in existing_block
    assert "MigrationImportRecord(" not in existing_block


def test_phase2_state_overrides_are_presence_aware() -> None:
    router = _text(ROUTER_PATH)
    service = _text(SERVICE_PATH)
    assert "traffic_limit_bytes: int | None = Field(default=None, ge=0)" in router
    assert "traffic_used_bytes: int | None = Field(default=None, ge=0)" in router
    assert 'elif "traffic_limit_bytes" in normalized:' in service
    assert 'elif "traffic_used_bytes" in normalized:' in service
    assert 'elif "expires_at" in normalized:' in service
    assert "limit_value if limit_present else 0" in service
    assert "used_value if used_present else 0" in service


def test_phase2_reimport_does_not_require_replacement_credentials() -> None:
    service = _text(SERVICE_PATH)
    existing_index = service.index("if existing:")
    credential_guard_index = service.index('if not links and not normalized.get("credentials")')
    assert existing_index < credential_guard_index


def test_phase2_preserves_payload_encrypted() -> None:
    service = _text(SERVICE_PATH)
    assert "preserved_payload_encrypted=_enc_payload(preserved)" in service
    assert "Fernet" in service
    assert "app_secret_key" in service


def test_single_record_import_service_remains_db_only() -> None:
    service = _text(SERVICE_PATH)
    forbidden = (
        "create_subscription_core(",
        "queue_subscription_enforcement(",
        "ssh_connect_saved(",
        "QuotaUsageEvent(",
        "ProtocolCredential(",
        "provision_subscription",
    )
    for token in forbidden:
        assert token not in service


def test_v2ray_batch_endpoint_requires_preserved_uuid_before_provisioning() -> None:
    router = _text(ROUTER_PATH)
    assert '@admin_router.post("/import-batch")' in router
    assert "uuid.UUID(value)" in router
    assert 'raise ValueError("preserved V2Ray UUID is missing from migration record")' in router
    assert 'raise ValueError("preserved V2Ray UUID is invalid")' in router
    assert 'subscription_uuids[int(result["subscription_id"])] = _preserved_v2ray_uuid(record)' in router
    assert "await provision_migrated_v2ray_batch(" in router


def test_v2ray_batch_provision_is_atomic_and_one_restart_per_node() -> None:
    service = _text(BATCH_SERVICE_PATH)
    assert "clients[:]=[item for item in clients if item.get('email') not in emails]" in service
    assert "clients.extend(payload)" in service
    assert "os.fsync(handle.fileno())" in service
    assert "os.replace(tmp,p)" in service
    assert '"email": f"mv-{subscription_id}@twinpanel"' in service
    assert "for node in nodes:" in service
    assert service.count("systemctl restart xray") == 1
    assert '"node_restarts": successful_nodes' in service


def test_v2ray_batch_writes_preserved_uuid_to_delivery_credential() -> None:
    service = _text(BATCH_SERVICE_PATH)
    assert 'client_id = str(subscription_uuids[subscription_id])' in service
    assert 'f"vless://{client_id}@{host}:{port}"' in service
    assert 'cred.config_text_encrypted = ad._enc(items)' in service
    assert "db.commit()" in service


def test_migration_admin_ui_uses_single_batch_request_for_v2ray() -> None:
    ui = _text(UI_PATH)
    assert '"/v1/admin/migration-center/import-batch"' in ui
    assert "records:readyRecords" in ui
    assert 'protocols:["v2ray"]' in ui
    assert "result.provision.node_restarts" in ui


def test_phase2_keeps_legacy_delivery_separate() -> None:
    router = _text(ROUTER_PATH)
    assert 'prefix="/v1/migration/legacy"' in router
    assert "base64.b64encode" in router
    assert "legacy_payload(db, token)" in router
    assert 'prefix="/admin/migration-center"' in router
    assert "dependencies=[Depends(require_admin)]" in router


def test_phase2_exposes_admin_import_history() -> None:
    router = _text(ROUTER_PATH)
    assert '@admin_router.get("/imports")' in router
    assert "MigrationImportRecord.created_at.desc()" in router
    assert '"subscription_id": marker.subscription_id' in router
    assert '"account_username": sub.account_username if sub else None' in router


def test_phase2_registration_does_not_rewrite_main() -> None:
    aggregate = _text(AGGREGATE_PATH)
    assert "migration_center_v2_admin_router.routes" in aggregate
    assert "migration_center_v2_public_router.routes" in aggregate
    assert "account_delivery_public_router.routes.extend" in aggregate


def test_phase2_share_code_only_binds_collision_free_token() -> None:
    service = _text(SERVICE_PATH)
    assert "len(token) <= 64" in service
    assert "Subscription.share_code == token" in service
    assert "if collision is None" in service
    assert "share_code=share_code" in service


def test_phase2_reports_reverse_proxy_requirement() -> None:
    service = _text(SERVICE_PATH)
    assert '"reverse_proxy_required": bool(legacy_url)' in service
    assert '"legacy_passthrough_path"' in service


if __name__ == "__main__":
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
    print(f"migration_center_v2_smoke: {len(tests)} passed")
