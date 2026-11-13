from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "app" / "routers" / "migration_center_v2.py"
UI = ROOT.parent / "components" / "migration-center-admin.tsx"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_target_preflight_is_admin_only_read_only_and_explicit() -> None:
    source = read(ROUTER)
    assert 'prefix="/admin/migration-center"' in source
    assert "dependencies=[Depends(require_admin)]" in source
    block = source.split('@admin_router.get("/target-check")', 1)[1].split(
        '@admin_router.get("/overview")', 1)[0]
    assert "user = db.get(User, target_user_id)" in block
    assert "existing_imports" in block
    assert "bool(user.is_active)" in block
    for forbidden in ("db.commit(", "db.add(", "db.delete(", "password_hash"):
        assert forbidden not in block


def test_overview_is_bounded_secret_free_and_avoids_n_plus_one() -> None:
    source = read(ROUTER)
    block = source.split('@admin_router.get("/overview")', 1)[1].split(
        '@admin_router.get("/imports")', 1)[0]
    assert "limit: int = Query(default=12, ge=1, le=30)" in block
    assert ".outerjoin(Subscription," in block
    assert ".limit(limit)" in block
    assert "MigrationImportRecord.source == source" in block
    for forbidden in ("legacy_token", "legacy_url", "preserved_payload_encrypted", "db.commit(", "db.add("):
        # They are allowed only in the docstring describing what must not be
        # returned. The serializer and queries must never access them.
        serialized = block.split('    return {', 1)[1]
        assert forbidden not in serialized


def test_ui_prevents_stale_preview_and_validates_target_before_write() -> None:
    ui = read(UI)
    assert 'result.writes_performed!==false' in ui
    assert 'dryRun.writes_performed!==false' in ui
    assert 'setRaw(event.target.value);setJsonFileName' in ui
    assert 'setSource(next);setDryRun(null)' in ui
    assert "const target=await checkTarget()" in ui
    assert "!target.exists||!target.active" in ui
    assert "const EYLAN_STAGE_CHUNK=50" in ui
    assert "const PREVIEW_PAGE_SIZE=20" in ui
    assert "MAX_JSON_BYTES=6*1024*1024" in ui


def test_ui_does_not_show_secrets_or_claim_provisioning_from_snapshots() -> None:
    ui = read(UI)
    assert "configuredCount" in ui
    assert "migrationStatus.fully_provisioned" in ui
    assert "Database snapshots are not the same as usable node configs." in ui
    assert "No passwords, tokens or private links." not in ui  # See exact UI text below
    assert "no passwords, tokens or private links." in ui
    assert "<td>{item.password}" not in ui
    assert "localStorage" not in ui
    assert "sessionStorage" not in ui


if __name__ == "__main__":
    tests = [
        f for name, f in sorted(globals().items())
        if name.startswith("test_") and callable(f)
    ]
    for test in tests:
        test()
    print(f"migration_center_v3_smoke: {len(tests)} passed")
