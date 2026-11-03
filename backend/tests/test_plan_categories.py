from app.plan_category_models import PlanCategoryAssignment
from app.routers.plans import DEFAULT_PLAN_CATEGORY, _normalize_category
from app.telegram_purchase_bot import category_plans, plan_categories, plan_category


def test_category_normalization_keeps_legacy_plans_compatible():
    assert _normalize_category(None) == DEFAULT_PLAN_CATEGORY
    assert _normalize_category("") == DEFAULT_PLAN_CATEGORY
    assert _normalize_category("  ویژه   ماهانه  ") == "ویژه ماهانه"


def test_category_assignment_is_unique_per_plan():
    column = PlanCategoryAssignment.__table__.c.plan_id
    assert column.unique is True
    assert column.nullable is False


def test_main_bot_groups_plans_by_category_with_legacy_fallback():
    plans = [
        {"id": 3, "name": "VIP", "category": "ویژه"},
        {"id": 2, "name": "Monthly", "category": "ماهانه"},
        {"id": 1, "name": "Legacy", "category": None},
    ]

    assert plan_category(plans[2]) == DEFAULT_PLAN_CATEGORY
    assert plan_categories(plans) == ["ویژه", "ماهانه", DEFAULT_PLAN_CATEGORY]

    category, rows = category_plans(plans, 1)
    assert category == "ماهانه"
    assert [row["id"] for row in rows] == [2]
