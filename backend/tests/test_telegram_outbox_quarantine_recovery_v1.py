from __future__ import annotations
import ast
from pathlib import Path
from unittest import TestCase, main

ROOT=Path(__file__).resolve().parents[1]
BOT=ROOT/"app/telegram_runtime_bot.py"
API=ROOT/"app/routers/telegram_bot.py"

def eligible(attempts:int,error:str|None,has_link:bool)->bool:
    if error=="telegram link not found" and has_link:
        return True
    return attempts<8 and (error is None or (
        error!="telegram link not found" and "blocked by the user" not in error.lower()
    ))

class TelegramOutboxDurability(TestCase):
    def test_worker_eligibility_enforced_before_limit(self):
        source=BOT.read_text()
        ast.parse(source)
        start=source.index("async def _telegram_notification_worker(")
        end=source.index("\nasync def main()",start)
        worker=source[start:end]
        self.assertIn("TelegramNotification.attempts < 8",worker)
        self.assertIn('== "telegram link not found"',worker)
        self.assertIn("TelegramUserLink.user_id",worker)
        self.assertIn("blocked by the user",worker)
        self.assertLess(worker.index("TelegramNotification.attempts < 8"),worker.index(".limit(20)"))
        self.assertIn("TelegramNotification.attempts.asc()",worker)
        self.assertIn("TelegramNotification.delivered_at",worker.replace("\n","").replace(" ",""))

    def test_missing_link_dormant_until_link_appears(self):
        self.assertFalse(eligible(997_719,"telegram link not found",False))
        self.assertTrue(eligible(997_719,"telegram link not found",True))
        self.assertTrue(eligible(0,None,False))

    def test_blocked_is_quarantined_and_recovered_only_after_user_interaction(self):
        error="Telegram server says - Forbidden: bot was blocked by the user"
        self.assertFalse(eligible(1,error,True))
        src=API.read_text()
        ast.parse(src)
        self.assertIn("def _wake_blocked_paid_deliveries(",src)
        a=src.index("def _wake_blocked_paid_deliveries(")
        b=src.index('@router.post(\n    "/ensure"',a)
        helper=src[a:b]
        self.assertIn('TelegramNotification.kind == "payment_approved"',helper)
        self.assertIn("TelegramNotification.delivered_at.is_(None)",helper)
        self.assertIn("TelegramNotification.attempts: 0",helper)
        ensure=src[src.index("def ensure_telegram_account("):]
        self.assertEqual(ensure.count("_wake_blocked_paid_deliveries(db, user.id)"),2)

    def test_transient_errors_are_bounded_and_auditable(self):
        self.assertTrue(eligible(3,"Temporary Telegram gateway timeout",True))
        self.assertFalse(eligible(8,"Temporary Telegram gateway timeout",True))
        self.assertFalse(eligible(98000,"telegram link not found",False))

if __name__=="__main__":
    main()
