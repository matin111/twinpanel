"""Regression: click-to-filter receipts never changes payment approval logic.

The purchase/wallet/KPI actions must be wired to read-only view filters;
opening receipt media retains authorized admin receipt endpoints.
"""
from pathlib import Path
from unittest import TestCase


REPO = Path(__file__).resolve().parents[2]
RUNTIME = (REPO / "components/payments-review-runtime.tsx").read_text()
SELECTORS = (REPO / "lib/payment-review-filters.ts").read_text()


class ClickableReviewFilterTests(TestCase):
    def test_each_kpi_is_a_real_accessible_button(self):
        for state in ("needs_review", "new_receipts",
                      "purchase_review", "wallet_review"):
            self.assertIn('id:"' + state + '"', RUNTIME)
            self.assertIn('case "' + state + '"', SELECTORS)
        self.assertIn('onClick={()=>selectFilter(item.id)}', RUNTIME)
        self.assertIn('aria-pressed={filter===item.id}', RUNTIME)
        self.assertIn('className={`card stat payment-review-filter-card', RUNTIME)

    def test_summary_counts_use_exact_same_filter_as_click_action(self):
        for key in ("pendingRows", "receiptRows",
                    "walletPending", "purchasePending"):
            self.assertIn("const " + key + "=rows.filter(row=>matchesPaymentReviewFilter(row,", RUNTIME)
        self.assertIn('if(!matchesPaymentReviewFilter(row,filter))return false;', RUNTIME)
        self.assertIn('setQuery(""); // Old search terms', RUNTIME)

    def test_receipts_are_file_backed_not_inferred_from_tracking_codes(self):
        self.assertIn("const hasReceipt=Boolean(row.receipt_uploaded);", RUNTIME)
        self.assertNotIn('Boolean(trackingCode)&&reviewStatuses', RUNTIME)
        self.assertIn('hasReceipt:Boolean(row.has_receipt)', RUNTIME)
        self.assertIn('onClick={()=>void openReceipt(row)}', RUNTIME)

    def test_authorized_receipt_endpoints_preserved(self):
        self.assertIn('/v1/admin/wallet/topups/${row.id}/receipt', RUNTIME)
        self.assertIn('/v1/payments/admin/intents/${row.id}/receipt', RUNTIME)
        self.assertIn('Authorization:`Bearer ${token}`', RUNTIME)

    def test_approvals_are_not_affected_by_filter_changes(self):
        self.assertIn('adminApi.approvePayment(row.id)', RUNTIME)
        self.assertIn('parityApi.walletApprove(row.id)', RUNTIME)
        self.assertIn('adminApi.rejectPayment(row.id,reason.trim())', RUNTIME)
        self.assertIn('parityApi.walletReject(row.id,reason.trim())', RUNTIME)
        self.assertIn('// TWINPANEL_PAYMENT_REVIEW_OPTIMISTIC_V2', RUNTIME)


if __name__ == "__main__":
    import unittest
    unittest.main()
