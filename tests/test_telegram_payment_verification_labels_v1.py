"""Regression: Telegram payment notifications must not label manual payments as automatic."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LABEL_PATH=ROOT/'backend/app/telegram_payment_labels.py'
BOT_PATH=ROOT/'backend/app/telegram_runtime_bot.py'


def _label(status):
    tree=ast.parse(LABEL_PATH.read_text(encoding='utf-8'))
    helper=next(n for n in tree.body if isinstance(n,ast.FunctionDef)
                and n.name=='payment_approved_heading')
    block=ast.Module(body=[helper],type_ignores=[])
    ast.fix_missing_locations(block)
    scope={}
    exec(compile(block,str(LABEL_PATH),'exec'),scope)
    return scope['payment_approved_heading'](status)


def test_manual_payment_heading_is_explicit():
    text=_label('approved')
    assert 'دستی' in text
    assert 'خودکار' not in text


def test_automatic_payment_heading_is_explicit():
    text=_label('auto_verified')
    assert 'خودکار' in text
    assert 'دستی' not in text


def test_missing_or_unknown_status_does_not_invent_verification_type():
    for status in (None,'','pending_payment','fulfilled'):
        text=_label(status)
        assert 'تأیید شد' in text
        assert 'دستی' not in text
        assert 'خودکار' not in text


def test_telegram_bot_uses_database_status_not_event_key():
    source=BOT_PATH.read_text(encoding='utf-8')
    compile(source,str(BOT_PATH),'exec')
    assert 'verification_status = payment_intent.status' in source
    assert 'payment_approved_heading(verification_status)' in source
    assert 'int(payment_intent.user_id) == int(row.user_id)' in source
