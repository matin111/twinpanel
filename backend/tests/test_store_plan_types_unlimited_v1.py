"""Contract regressions for storefront subscription types and zero=unlimited users.

These tests do not need a running database, server, or customer accounts.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_zero_is_preserved_through_plan_validation_and_api():
    schemas = source("backend/app/schemas.py")
    plans = source("backend/app/routers/plans.py")
    assert "device_limit: int = Field(default=1, ge=0)" in schemas
    assert "device_limit: int | None = Field(default=None, ge=0)" in schemas
    assert "int(plan.device_limit if plan.device_limit is not None else 1)" in plans


def test_zero_removes_quota_concurrency_cap_but_keeps_nonzero_caps():
    quota = source("backend/app/quota_service.py")
    assert "if max_sessions > 0 and active_count >= max_sessions:" in quota
    assert "if max_sessions > 0 and active_count >= max_sessions:" in source("backend/app/quota_service_v2.py")
    assert "max(int(plan.device_limit if plan and plan.device_limit is not None else 1), 0)" in quota


def test_subscriptions_do_not_silently_convert_unlimited_to_one():
    override = source("backend/app/subscription_override_models.py")
    normal = source("backend/app/routers/subscription_admin_v2.py")
    fast = source("backend/app/routers/subscription_create_fast_v1.py")
    assert "return max(int(override.device_limit), 0)" in override
    assert "device_limit=max(0, device_limit)" in normal
    assert "device_limit=max(0, device_limit)" in fast
    assert "if device_limit > 0 and active_devices > device_limit:" in source("backend/app/routers/admin.py")


def test_type_selection_precedes_user_count_in_storefront():
    tabs = source("components/plan-category-tabs.tsx")
    store = source("components/store-runtime.tsx")
    assert "data-plan-type-tabs" in tabs
    assert tabs.index("data-plan-type-tabs") < tabs.index("data-plan-user-count-tabs")
    assert "normalizePlanType(plan.subscription_type)" in tabs
    assert "const typedPlans=useMemo(()=>filterPlansByType" in store
    assert "planCategories(typedPlans)" in store
    assert 'deviceLimit===0?"کاربر نامحدود"' in tabs


def test_all_four_templates_display_unlimited_instead_of_zero():
    for path in (
        "components/store-template-renderer.tsx",
        "components/store-template-editorial-grid.tsx",
        "components/store-template-editorial-pro.tsx",
        "components/store-template-orbit-neo.tsx",
    ):
        assert 'plan.device_limit===0?pick("کاربر نامحدود","Unlimited users")' in source(path)


def test_admin_can_assign_plan_type_and_zero_user_limit():
    admin = source("components/legacy-plans-exact.tsx")
    assert 'pick("نوع اشتراک","Subscription type")' in admin
    assert "min={0} value={draft.device_limit}" in admin
    assert 'pick("تعداد کاربر (۰ = نامحدود)","Users (0 = unlimited)")' in admin


def test_color_icons_per_subscription_type():
    tabs = source("components/plan-category-tabs.tsx")
    assert "planTypeAppearance(name,index)" in tabs
    assert "v2ray|xray" in tabs
    assert "ویژه|vip|premium" in tabs

def test_new_subscription_type_is_independent_of_legacy_category():
    model = source("backend/app/plan_category_models.py")
    api = source("backend/app/routers/plans.py")
    assert "ADD COLUMN IF NOT EXISTS subscription_type VARCHAR(120)" in model
    assert "subscription_type: Mapped[str]" in model
    assert '"category": _plan_category(db, int(plan.id))' in api
    assert '"subscription_type": _plan_subscription_type(db, int(plan.id))' in api
    assert '_set_plan_category(db, int(plan.id), raw.get("category"))' in api
    assert '_set_plan_subscription_type(db, int(plan.id), raw.get("subscription_type"))' in api
    assert 'if "subscription_type" in raw:' in api
    assert 'values.pop("subscription_type", None)' in api
    admin = source("components/legacy-plans-exact.tsx")
    assert 'subscription_type:s(row.subscription_type)' in admin
    assert 'value={draft.subscription_type}' in admin


def test_legacy_category_icons_have_distinct_colors():
    tabs = source("components/plan-category-tabs.tsx")
    assert "function userCountAppearance(category:string,index:number)" in tabs
    assert "const accent=userCountAppearance(category,index);" in tabs
    assert "background:accent.background" in tabs
    assert 'normalizePlanType(plan.subscription_type)===type' in tabs
    assert 'normalizePlanType(plan.category)===type' not in tabs


def test_type_assignment_does_not_duplicate_the_plan_category_row():
    api = source("backend/app/routers/plans.py")
    assert (
        '_set_plan_category(db, int(plan.id), raw.get("category"))\n'
        "    db.flush()"
    ) in api
    assert (
        '_set_plan_category(db, int(plan.id), raw.get("category"))\n'
        "        db.flush()"
    ) in api
