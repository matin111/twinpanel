from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UI_PATH = ROOT / "components" / "migration-center-admin.tsx"


def test_migration_history_is_not_loaded_into_page() -> None:
    ui = UI_PATH.read_text(encoding="utf-8")
    assert '"/v1/admin/migration-center/imports"' not in ui
    assert "Previous imports" not in ui
    assert "وضعیت انتقال‌های قبلی" not in ui
    assert "useEffect" not in ui


def test_import_result_is_session_only() -> None:
    ui = UI_PATH.read_text(encoding="utf-8")
    assert "بعد از رفرش این نتیجه از صفحه پاک می‌شود" in ui
    assert "Import results are shown only for this session and clear on refresh" in ui


if __name__ == "__main__":
    test_migration_history_is_not_loaded_into_page()
    test_import_result_is_session_only()
    print("migration_center_session_ui_smoke: 2 passed")
