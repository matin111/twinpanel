"""Regression gate for one-tap receipt approval and same-message status refresh."""
from pathlib import Path
import ast
import unittest

ROOT=Path(__file__).resolve().parents[1]
BOT=ROOT/"app/telegram_admin_ops_v1.py"
PUSH=ROOT/"app/services/telegram_admin_receipt_push.py"
API=ROOT/"app/routers/telegram_admin_ops_v1.py"


def section(src, start, stop):
    return src[src.index(start):src.index(stop,src.index(start))]


class ReceiptOneTapAndInPlace(unittest.TestCase):
    def test_sources_parse(self):
        for file in (BOT,PUSH,API):
            ast.parse(file.read_text(encoding="utf-8"))

    def test_new_receipt_buttons_approve_directly(self):
        source=PUSH.read_text()
        self.assertIn('f"adm:do:approve:{kind}:{item_id}"',source)
        self.assertNotIn('f"adm:ask:approve:{kind}:{item_id}"',source)
        self.assertIn('f"adm:r:{kind}:{item_id}"',source)

    def test_status_refresh_edits_same_message_without_new_media(self):
        src=BOT.read_text()
        part=section(src,'    async def receipt_detail(', '    async def _finalize_receipt_message(')
        self.assertIn('callback.message.edit_caption(',part)
        self.assertIn('callback.message.edit_text(',part)
        self.assertIn('GET", f"/receipt/',part)
        self.assertNotIn('answer_photo(',part)
        self.assertNotIn('answer_document(',part)
        self.assertNotIn('callback.message.answer(',part)
        self.assertNotIn('BufferedInputFile(',part)
        self.assertIn('if data.get("can_approve") and data.get("has_receipt"):',part)
        self.assertIn('("✅ تأیید رسید", f"adm:do:approve:',part)

    def test_old_approval_buttons_skip_confirmation(self):
        src=BOT.read_text()
        old=section(src,'    async def sensitive_preview(', '    @router.callback_query(F.data.startswith("adm:do:"))')
        self.assertIn('pieces[2] == "approve"',old)
        self.assertIn('await sensitive_execute(',old)
        self.assertIn('direct_data=',old)

    def test_receipt_action_reuses_financial_api_not_new_order(self):
        src=BOT.read_text()
        part=section(src,'    async def sensitive_execute(', '    @router.callback_query(F.data == "adm:lookup")')
        self.assertIn('POST", f"/receipt/{kind}/{item_id}/{action}"',part)
        self.assertIn('await _finalize_receipt_message(callback.message, detail)',part)
        self.assertIn('if kind not in ("purchase", "wallet"):',part)
        self.assertNotIn('POST", "/v1/orders',part)
        self.assertNotIn('POST", "/v1/wallet/topups',part)

    def test_approved_wallet_receipt_still_has_readonly_status(self):
        src=API.read_text()
        part=section(src,'@router.get("/receipt/{telegram_id}/{kind}/{item_id}")', '@router.post("/receipt/{kind}/{item_id}/approve")')
        self.assertIn('row = db.get(CustomerWalletTopup, item_id)',part)
        self.assertIn('"can_approve": _manual_topup(row)',part)
        self.assertNotIn('or not _manual_topup(row)',part)
        self.assertIn('receipt_file_marker',part)

    def test_backend_approval_remains_canonical_and_gated(self):
        src=API.read_text()
        part=section(src,'@router.post("/receipt/{kind}/{item_id}/approve")', '@router.post("/receipt/{kind}/{item_id}/reject")')
        self.assertIn('actor = _admin(db, payload.telegram_id)',part)
        self.assertIn('if not _manual_purchase(row):',part)
        self.assertIn('approve_payment_fast(item_id, background_tasks, db)',part)
        self.assertIn('approve_wallet_topup_v2(item_id, db)',part)
        self.assertIn('if not row.receipt_telegram_file_id:',part)


if __name__=="__main__":
    unittest.main()
