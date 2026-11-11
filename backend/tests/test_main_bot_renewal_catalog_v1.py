"""Main customer bot renewal plan selection and click safety regressions."""
import unittest

from app.telegram_renewal_catalog_main_v1 import (
    eligible_renewal_plans,
    renewal_stage_markup,
    load_renewal_catalog,
    load_selected_renewal_plan,
)


FIXTURES = [
    {"id": 301, "name": "اقتصادی 30", "subscription_type": "اقتصادی",
     "device_limit": 1, "category": "ماهانه", "duration_days": 30,
     "traffic_gb": 30, "price_toman": 50000, "is_active": True},
    {"id": 302, "name": "اقتصادی 60", "subscription_type": "اقتصادی",
     "device_limit": 1, "category": "ماهانه", "duration_days": 30,
     "traffic_gb": 60, "price_toman": 90000, "is_active": True},
    {"id": 303, "name": "اقتصادی بلندمدت", "subscription_type": "اقتصادی",
     "device_limit": 1, "category": "سه ماهه", "duration_days": 90,
     "traffic_gb": 90, "price_toman": 150000, "is_active": True},
    {"id": 304, "name": "ویژه 2", "subscription_type": "ویژه",
     "device_limit": 2, "category": "ماهانه", "duration_days": 30,
     "traffic_gb": 60, "price_toman": 190000, "is_active": True},
    {"id": 305, "name": "__tp_reseller__internal", "subscription_type": "ویژه",
     "device_limit": 2, "category": "ماهانه", "duration_days": 30,
     "traffic_gb": 60, "price_toman": 1, "is_active": True},
    {"id": 306, "name": "غیرفعال", "subscription_type": "ویژه",
     "device_limit": 2, "category": "ماهانه", "duration_days": 30,
     "traffic_gb": 60, "price_toman": 190000, "is_active": False},
    {"id": 307, "name": "رایگان", "subscription_type": "اقتصادی",
     "device_limit": 1, "category": "ماهانه", "duration_days": 30,
     "traffic_gb": 60, "price_toman": 0, "is_active": True},
]


def callback_data(markup):
    return [
        b.callback_data for row in markup.inline_keyboard for b in row
    ]


class RenewalCatalogTests(unittest.IsolatedAsyncioTestCase):
    def test_active_paid_public_plans_only(self):
        self.assertEqual(
            [p["id"] for p in eligible_renewal_plans(FIXTURES)],
            [301, 302, 303, 304],
        )

    def test_type_then_devices_then_category_then_new_plan(self):
        plans = eligible_renewal_plans(FIXTURES)
        text, buttons = renewal_stage_markup(plans, 44)
        self.assertIn("نوع اشتراک", text)
        self.assertIn("subrntype:44:0", callback_data(buttons))
        text, buttons = renewal_stage_markup(plans, 44, "users", type_index=0)
        self.assertIn("subrnusers:44:0:1", callback_data(buttons))
        text, buttons = renewal_stage_markup(
            plans, 44, "category", type_index=0, user_count=1,
        )
        self.assertIn("subrncat:44:0:1:0", callback_data(buttons))
        self.assertIn("subrncat:44:0:1:1", callback_data(buttons))
        text, buttons = renewal_stage_markup(
            plans, 44, "plans", type_index=0, user_count=1,
            category_index=0,
        )
        ids = callback_data(buttons)
        self.assertIn("subrnplan:44:301", ids)
        self.assertIn("subrnplan:44:302", ids)
        self.assertNotIn("subrnplan:44:304", ids)

    def test_invalid_route_indices_rejected(self):
        plans = eligible_renewal_plans(FIXTURES)
        with self.assertRaises(ValueError):
            renewal_stage_markup(plans, 44, "users", type_index=777)
        with self.assertRaises(ValueError):
            renewal_stage_markup(plans, 44, "plans", type_index=0, user_count=2, category_index=0)

    async def test_user_must_own_renewable_subscription(self):
        async def no_access(_user, _sub):
            return "token", {"can_renew": False}

        async def get(*_):
            return FIXTURES

        with self.assertRaises(ValueError):
            await load_renewal_catalog(8, 44, request_fn=get, load_manage_fn=no_access)

    async def test_selected_public_plan_reloaded_and_price_available(self):
        async def manage(_user, _sub):
            return "token", {"can_renew": True}

        async def get(*_):
            return FIXTURES

        result = await load_selected_renewal_plan(
            8, 44, 304, request_fn=get, load_manage_fn=manage,
        )
        self.assertEqual(result["price_toman"], 190000)
        self.assertEqual(result["duration_days"], 30)
        with self.assertRaises(ValueError):
            await load_selected_renewal_plan(
                8, 44, 305, request_fn=get, load_manage_fn=manage,
            )


if __name__ == "__main__":
    unittest.main()
