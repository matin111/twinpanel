from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_mother_route_uses_unified_editor() -> None:
    routed = _source("components/routed-page-client.tsx")
    editor = _source("components/mother-access-runtime-v3.tsx")

    assert 'import("./mother-access-runtime-v3")' in routed
    assert "MotherAccessRuntimeV3" in routed
    assert "نام سرور مادر" in editor
    assert "دامنه عمومی سرور مادر" in editor
    assert "نمایش سرور مادر در اشتراک‌های مدیر" in editor
    assert "سرور مادر هیچ‌وقت وارد Multi-Link نمی‌شود" in editor


def test_mother_settings_share_the_canonical_api() -> None:
    editor = _source("components/mother-access-runtime-v3.tsx")
    api = _source("lib/general-settings-api.ts")
    policy = _source("backend/app/mother_subscription_delivery_policy_v108.py")

    assert "generalSettingsApi.saveMotherAccess" in editor
    assert "mother_name?:string" in api
    assert "public_domain?:string" in api
    assert "TWINPANEL_MOTHER_SUBSCRIPTION_DELIVERY_POLICY_V113" in policy
    assert "Mother is never a HA/Multi-Link member" in policy
    assert "account_delivery._stored_info = _stored_info_with_mother_policy" in policy
