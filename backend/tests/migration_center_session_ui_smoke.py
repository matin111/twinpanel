from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UI_PATH = ROOT / "components" / "migration-center-admin.tsx"


def test_safe_history_does_not_fetch_legacy_secret_endpoints() -> None:
    ui = UI_PATH.read_text(encoding="utf-8")
    assert '"/v1/admin/migration-center/imports"' not in ui
    assert "/v1/admin/migration-center/overview?source=" in ui
    assert "legacy_token" not in ui
    assert "preserved_payload_encrypted" not in ui
    assert "useEffect" in ui


def test_current_results_remain_session_only() -> None:
    ui = UI_PATH.read_text(encoding="utf-8")
    assert "بعد از رفرش این نتیجه از صفحه پاک می‌شود" in ui
    assert "Import results are shown only for this session and clear on refresh" in ui
    assert "localStorage" not in ui
    assert "sessionStorage" not in ui


def test_sensitive_source_input_invalidates_preview() -> None:
    ui = UI_PATH.read_text(encoding="utf-8")
    assert "setRaw(event.target.value);setJsonFileName" in ui
    assert "setDryRun(null);setPreviewPage(0)" in ui
    assert "dryRun.writes_performed!==false" in ui
    assert "await checkTarget()" in ui
    assert "/v1/admin/migration-center/target-check?source=" in ui
    assert "PREVIEW_PAGE_SIZE=20" in ui


if __name__ == "__main__":
    tests = (test_safe_history_does_not_fetch_legacy_secret_endpoints,
             test_current_results_remain_session_only,
             test_sensitive_source_input_invalidates_preview)
    for test in tests:
        test()
    print(f"migration_center_session_ui_smoke: {len(tests)} passed")
