"""Protect the discount editor against hidden network errors and lost forms."""

import unittest
from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[2]
    / "components"
    / "admin-parity-runtime.tsx"
).read_text(encoding="utf-8")

DISCOUNTS = SOURCE.split("export function DiscountsRuntimePage(){", 1)[1].split(
    "function valueNullableNumber", 1
)[0]


class DiscountNetworkFeedbackTests(unittest.TestCase):
    def test_request_errors_are_visible_inside_modal(self):
        self.assertIn('className="discount-modal-feedback" role="alert"', DISCOUNTS)
        self.assertIn("setModalError(friendlyError(e))", DISCOUNTS)
        self.assertIn("setModalError(pick(", DISCOUNTS)

    def test_failed_save_keeps_form_for_manual_retry(self):
        self.assertIn("try{await fn();", DISCOUNTS)
        self.assertIn("}catch(e){if(open)setModalError", DISCOUNTS)
        self.assertIn('type="submit" className="primary" disabled={busy}', DISCOUNTS)

    def test_network_retries_are_read_only(self):
        self.assertIn("retryRead(parityApi.discounts)", DISCOUNTS)
        self.assertIn("retryRead(adminApi.plans)", DISCOUNTS)
        self.assertIn("()=>parityApi.discountCreate(payload)", DISCOUNTS)
        self.assertNotIn("retryRead(parityApi.discountCreate", DISCOUNTS)

    def test_no_fake_zero_stats_when_list_fails(self):
        self.assertIn('rowsLoaded?String(rows.length):"—"', DISCOUNTS)
        self.assertIn("setRowsLoaded(false)", DISCOUNTS)


if __name__ == "__main__":
    unittest.main()
