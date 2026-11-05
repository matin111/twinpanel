"""Regression: admin button visibility must depend on the current recipient grant."""
import ast
from pathlib import Path
from typing import Any
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Extract only the pure presentation method: this CI environment does not
# initialize the live application database, settings, or node runtimes.
source = (Path(__file__).resolve().parents[1] / "app" / "bot_text_middleware.py").read_text()
module = ast.parse(source)
cls = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "BotTextRequestMiddleware")
func = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "_add_navigation")
namespace = {"Any": Any, "InlineKeyboardButton": InlineKeyboardButton, "InlineKeyboardMarkup": InlineKeyboardMarkup}
exec(compile(ast.Module(body=[func], type_ignores=[]), "<admin-home>", "exec"), namespace)

class BotTextRequestMiddleware:
    def __init__(self, scope): self.scope=scope
    _add_navigation=namespace["_add_navigation"]
    _navigation_back=staticmethod(lambda text, scope: "main:home")

home_callbacks=["shop:list","trial:claim","main:dashboard","subs:list"]
home_markup=InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text=name,callback_data=name)] for name in home_callbacks
])
m=BotTextRequestMiddleware(scope="admin")
orig=m._is_verified_admin_chat
try:
    m._is_verified_admin_chat=lambda chat: int(chat)==42
    def callbacks(chat,markup=home_markup):
        result=m._add_navigation(SendMessage(chat_id=chat,text="سلام",reply_markup=markup))
        return [b.callback_data for row in result.reply_markup.inline_keyboard for b in row]
    assert "adm:home" in callbacks(42)
    assert callbacks(42).count("adm:home")==1
    assert "adm:home" not in callbacks(43)
    assert "main:home" not in callbacks(43)
    nonhome=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="اکانت",callback_data="subs:list")]
    ])
    assert "adm:home" not in callbacks(42,nonhome)
    m.scope="reseller"
    assert "adm:home" not in callbacks(42)
finally:
    m._is_verified_admin_chat=orig
print("ADMIN_HOME_BUTTON_VISIBILITY=PASS")
