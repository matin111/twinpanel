"""The Telegram bot should use subdued, single-accent navigation controls."""
import unittest

from aiogram.types import InlineKeyboardButton

from app.telegram_account_link_bot_original import (
    _cancel_keyboard,
    _connect_keyboard,
    _main_menu_keyboard,
)
from app.telegram_expiry_notification_ui_v1 import _expiry_keyboard
from app.telegram_purchase_bot import (
    categories_keyboard,
    category_icon,
    user_count_icon,
)
from app.telegram_subscription_ui_patch_v1 import _decorate, _pretty_button
from app.telegram_subscription_import_bot_v1 import _navigation
from app.telegram_renewal_catalog_main_v1 import (
    renewal_plan_button_label,
    renewal_stage_markup,
)


def buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


class MinimalBotThemeTests(unittest.TestCase):
    def test_main_menu_one_primary_no_green_or_red_navigators(self):
        markup = _main_menu_keyboard()
        colored = [b for b in buttons(markup) if b.style]
        self.assertEqual(len(colored), 1)
        self.assertEqual(colored[0].style, "primary")
        self.assertEqual(colored[0].callback_data, "shop:list")

    def test_connect_menu_only_one_accent(self):
        markup = _connect_keyboard()
        self.assertEqual([b.style for b in buttons(markup)], ["primary", None])
        self.assertTrue(all(b.style is None for b in buttons(_cancel_keyboard())))

    def test_categories_and_device_counts_are_not_rainbow_colored(self):
        self.assertEqual(user_count_icon(1), user_count_icon(8))
        self.assertEqual(category_icon("۱ ماهه", 1), "")
        self.assertEqual(category_icon("💎 حرفه‌ای", 2), "")
        plan = {
            "id": 401, "subscription_type": "حرفه‌ای",
            "category": "۱ ماهه", "device_limit": 3,
            "duration_days": 30, "traffic_gb": 30,
            "price_toman": 450000, "is_active": True,
            "name": "۳۰ گیگ",
        }
        _, markup = renewal_stage_markup(
            [plan], 3800, "category", type_index=0, user_count=3,
        )
        self.assertEqual(buttons(markup)[0].text, "۱ ماهه")
        self.assertEqual(buttons(markup)[0].style, None)

    def test_subscription_actions_use_only_one_accent(self):
        renew = _pretty_button(InlineKeyboardButton(
            text="تمدید اکانت", callback_data="subrenew:39",
        ))
        self.assertIsNone(renew.style)
        link = _pretty_button(InlineKeyboardButton(
            text="اطلاعات اتصال", callback_data="subconn:39",
        ))
        self.assertEqual(link.style, "primary")
        protocol = _pretty_button(InlineKeyboardButton(
            text="WireGuard", callback_data="proto:wireguard",
        ))
        self.assertIsNone(protocol.style)
        delete = _pretty_button(InlineKeyboardButton(
            text="حذف اشتراک", callback_data="subdelete:39",
        ))
        self.assertEqual(delete.style, "danger")

    def test_notification_action_accent_not_home(self):
        markup = _expiry_keyboard(39)
        self.assertEqual(buttons(markup)[0].style, "primary")
        self.assertTrue(all(b.style is None for b in buttons(markup)[1:]))

    def test_imported_account_back_buttons_are_neutral(self):
        self.assertTrue(all(b.style is None for b in buttons(_navigation())))

    def test_plan_price_stays_the_same(self):
        plan = {"name": "۳۰ گیگ", "price_toman": 450000}
        self.assertEqual(
            renewal_plan_button_label(plan),
            "۳۰ گیگ  |  450,000 تومان",
        )


if __name__ == "__main__":
    unittest.main()
