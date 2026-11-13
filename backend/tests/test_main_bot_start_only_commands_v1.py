"""Regression checks for Telegram command-menu migration across panel installs."""
from pathlib import Path
import ast
import unittest
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"backend/app/bot_text_middleware.py"
class MainBotMenuTests(unittest.TestCase):
    def test_code_compiles(self):
        ast.parse(SOURCE.read_text())
    def test_main_bot_clears_legacy_scopes_and_languages(self):
        code=SOURCE.read_text()
        for name in ("BotCommandScopeDefault","BotCommandScopeAllPrivateChats","BotCommandScopeAllGroupChats","BotCommandScopeAllChatAdministrators"):
            self.assertIn(name+"()",code)
        self.assertIn('languages = (None, "fa", "en")',code)
        self.assertIn('commands = [BotCommand(command="start", description="شروع ربات")]',code)
        self.assertIn('if self.scope == "admin":',code)
        self.assertIn('SetMyCommands(',code)
        self.assertIn('self._commands_sync_attempted = not failed',code)
    def test_existing_linked_users_migrate_without_chat_messages(self):
        code=SOURCE.read_text()
        self.assertIn('BotCommandScopeChat(chat_id=chat_id)',code)
        self.assertIn('TelegramUserLink.telegram_id',code)
        self.assertIn('asyncio.create_task(',code)
        self.assertIn('await asyncio.sleep(0.15)',code)
        self.assertIn('telegram-start-only-menu-v1.sha256',code)
        self.assertIn('stamp.write_text(fingerprint +',code)
        self.assertNotIn('SendMessage(',code.split('async def _migrate_linked_chat_commands(')[1].split('def _load(')[0])

    def test_reseller_menus_remain_independent(self):
        code=SOURCE.read_text()
        self.assertIn('SetMyCommands(commands=[*commands, *current])',code)
if __name__=="__main__":
    unittest.main()
