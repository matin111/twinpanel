"""Regression: admin button visibility must depend on the current recipient grant."""
from pathlib import Path
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.bot_text_middleware import BotTextRequestMiddleware

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
