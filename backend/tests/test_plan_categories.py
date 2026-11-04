from app.models import Plan
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
    plan_subscription_type,
    subscription_types,
    subscription_type_plans,
    subscription_types_keyboard,
    user_count_icon,
    category_icon,
)


def test_category_normalization_keeps_legacy_plans_compatible():
    assert _normalize_category(None) == DEFAULT_PLAN_CATEGORY
    assert _normalize_category("") == DEFAULT_PLAN_CATEGORY
    assert _normalize_category("  ویژه   ماهانه  ") == "ویژه ماهانه"


def test_category_assignment_is_unique_per_plan():
    column = PlanCategoryAssignment.__table__.c.plan_id
    assert column.unique is True
    assert column.nullable is False


def test_plan_name_is_not_unique_identity():
    assert Plan.__table__.c.name.unique is False
    name_unique_constraints = [
        constraint
        for constraint in Plan.__table__.constraints
        if getattr(constraint, "columns", None)
        and [column.name for column in constraint.columns] == ["name"]
    ]
    assert name_unique_constraints == []


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

def test_zero_user_count_is_unlimited_and_not_converted_to_one():
    unlimited = {"id": 99, "device_limit": 0, "category": "اشتراک ویژه"}
    normal = {"id": 100, "device_limit": 1, "category": "اشتراک ویتوری"}
    assert plan_user_count(unlimited) == 0
    assert user_counts([unlimited, normal]) == [0, 1]
    keyboard = user_counts_keyboard([unlimited, normal])
    assert "کاربر نامحدود" in keyboard.inline_keyboard[0][0].text
    assert keyboard.inline_keyboard[0][0].callback_data == "shop:users:0"
    assert [p["id"] for p in user_count_plans([unlimited, normal], 0)] == [99]


def test_subscription_types_are_first_level_without_changing_existing_categories():
    plans = [
        {"id": 1, "name": "Basic", "subscription_type": "اشتراک عمومی", "category": "یک ماهه", "device_limit": 1},
        {"id": 2, "name": "Special", "subscription_type": "اشتراک ویژه", "category": "یک ماهه", "device_limit": 1},
        {"id": 3, "name": "Premium", "subscription_type": "اشتراک ویژه", "category": "سه ماهه", "device_limit": 2},
    ]
    assert subscription_types(plans) == ["اشتراک عمومی", "اشتراک ویژه"]
    assert plan_subscription_type({"category": "متفاوت"}) == "اشتراک عمومی"
    title, selected = subscription_type_plans(plans, 1)
    assert title == "اشتراک ویژه"
    assert [plan["id"] for plan in selected] == [2, 3]
    assert plan_categories(selected) == ["یک ماهه", "سه ماهه"]
    keyboard = subscription_types_keyboard(plans)
    assert keyboard.inline_keyboard[0][0].callback_data == "shop:type:0"
    assert keyboard.inline_keyboard[1][0].callback_data == "shop:type:1"
    assert "💎" in keyboard.inline_keyboard[1][0].text


def test_typed_user_counts_and_colored_legacy_category_buttons_preserve_navigation():
    plans = [
        {"id": 36, "subscription_type": "اشتراک ویژه", "category": "💎 پلن حرفه‌ای ۲ ماهه", "device_limit": 1},
        {"id": 37, "subscription_type": "اشتراک ویژه", "category": "💎 پلن حرفه‌ای ۲ ماهه", "device_limit": 2},
        {"id": 10, "subscription_type": "اشتراک عمومی", "category": "یک ماهه", "device_limit": 1},
    ]
    special_index = subscription_types(plans).index("اشتراک ویژه")
    _type, special = subscription_type_plans(plans, special_index)
    assert "🟢" in user_count_icon(1)
    assert "🔵" in user_count_icon(2)
    assert "♾️" in user_count_icon(0)
    assert "📂" in category_icon("یک ماهه", 0)
    assert "💎" in category_icon("پلن ویژه", 0)
    typed_users = user_counts_keyboard(special, type_index=special_index)
    assert typed_users.inline_keyboard[0][0].callback_data == f"shop:tusers:{special_index}:1"
    typed_categories = categories_keyboard(special, user_count=1, type_index=special_index)
    assert typed_categories.inline_keyboard[0][0].callback_data == f"shop:tucat:{special_index}:1:0"
    assert typed_categories.inline_keyboard[-1][0].callback_data == f"shop:type:{special_index}"
