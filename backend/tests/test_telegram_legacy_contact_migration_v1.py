"""Non-destructive legacy bot audience import and opt-in activation guards."""
import ast
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
MODEL=(ROOT/"backend/app/telegram_legacy_contacts_v1.py").read_text()
RUNTIME=(ROOT/"backend/app/telegram_runtime_bot.py").read_text()
class TestLegacyTelegramAudience(unittest.TestCase):
    def test_compiles(self):
        ast.parse(MODEL)
        ast.parse(RUNTIME)
    def test_no_automatic_start_or_outbound_message(self):
        self.assertIn("acknowledge_legacy_start, int(message.from_user.id)",RUNTIME)
        self.assertIn("UPDATE telegram_legacy_contacts",MODEL)
        self.assertNotIn("send_message(",MODEL)
        self.assertNotIn("TelegramUserLink(",MODEL)
        self.assertNotIn("INSERT INTO users",MODEL)
    def test_idempotent_safe_import(self):
        self.assertIn("PRIMARY KEY",MODEL)
        self.assertIn("ON CONFLICT (telegram_id) DO NOTHING",MODEL)
        self.assertIn("telegram_user_links",MODEL)
        self.assertIn("RETURNING telegram_id",MODEL)
if __name__ == "__main__":
    unittest.main()
