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
    def test_reseller_menus_remain_independent(self):
        code=SOURCE.read_text()
        self.assertIn('SetMyCommands(commands=[*commands, *current])',code)
if __name__=="__main__":
    unittest.main()
