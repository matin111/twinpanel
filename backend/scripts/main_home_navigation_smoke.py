"""Confirm that only the main bot home menu skips redundant navigation."""
import ast
from pathlib import Path
from typing import Any
from aiogram.methods import SendMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

source=(Path(__file__).resolve().parents[1]/"app"/"bot_text_middleware.py").read_text()
tree=ast.parse(source)
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="BotTextRequestMiddleware")
fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=="_add_navigation")
exec(compile(ast.Module(body=[fn],type_ignores=[]),"<navigation>", "exec"),namespace:={**globals()})
class Stub:
    scope="main"
    _navigation_back=staticmethod(lambda text,scope:"main:home")
    _add_navigation=namespace["_add_navigation"]
stub=Stub()
home_callbacks=["shop:list","trial:claim","main:dashboard","subs:list","wallet:refresh"]
home=SendMessage(chat_id=123,text="خوش آمدید",reply_markup=InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text=cb,callback_data=cb)] for cb in home_callbacks
]))
result=stub._add_navigation(home)
assert result is home, "Home menu must not get Back/Home buttons"
sub=SendMessage(chat_id=123,text="اطلاعات اشتراک",reply_markup=InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="تمدید",callback_data="subrenew:1")]
]))
sub_result=stub._add_navigation(sub)
buttons=[b.callback_data for row in sub_result.reply_markup.inline_keyboard for b in row]
assert "main:home" in buttons and len(buttons)==3,buttons
print("MAIN_HOME_NO_REDUNDANT_NAV=PASS")
