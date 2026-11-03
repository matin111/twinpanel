from app.plan_category_models import PlanCategoryAssignment
from app.routers.plans import DEFAULT_PLAN_CATEGORY, _normalize_category
from app.telegram_purchase_bot import (
    categories_keyboard,
    category_plans,
    plan_categories,
    plan_category,
    plan_user_count,
    user_count_plans,
    user_counts,
    user_counts_keyboard,
)


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


def test_main_bot_groups_by_user_count_before_plan_category():
    plans = [
        {"id": 1, "device_limit": 1, "category": "یک ماهه"},
        {"id": 2, "device_limit": 1, "category": "دو ماهه"},
        {"id": 3, "device_limit": 2, "category": "یک ماهه"},
        {"id": 4, "device_limit": 2, "category": "سه ماهه"},
    ]

    assert plan_user_count({"device_limit": None}) == 1
    assert user_counts(plans) == [1, 2]
    assert [row["id"] for row in user_count_plans(plans, 2)] == [3, 4]

    category, rows = category_plans(plans, 0, user_count=2)
    assert category == "یک ماهه"
    assert [row["id"] for row in rows] == [3]


def test_main_bot_two_level_keyboard_callbacks_are_stable():
    plans = [
        {"id": 1, "device_limit": 1, "category": "یک ماهه"},
        {"id": 2, "device_limit": 2, "category": "یک ماهه"},
        {"id": 3, "device_limit": 2, "category": "دو ماهه"},
    ]

    user_keyboard = user_counts_keyboard(plans)
    assert user_keyboard.inline_keyboard[0][0].callback_data == "shop:users:1"
    assert user_keyboard.inline_keyboard[1][0].callback_data == "shop:users:2"

    category_keyboard = categories_keyboard(plans, user_count=2)
    assert category_keyboard.inline_keyboard[0][0].callback_data == "shop:ucat:2:0"
    assert category_keyboard.inline_keyboard[1][0].callback_data == "shop:ucat:2:1"
    assert category_keyboard.inline_keyboard[-1][0].callback_data == "shop:list"
