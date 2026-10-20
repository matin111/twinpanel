from app.bot_text_middleware import BotTextRequestMiddleware
from app.bot_texts import _setting_key


def _middleware(scope: str, values: dict[str, str]) -> BotTextRequestMiddleware:
    middleware = BotTextRequestMiddleware(scope=scope)
    middleware._load = lambda: values  # type: ignore[method-assign]
    return middleware


def test_bot_text_keys_are_isolated_by_owner():
    assert _setting_key("admin", "welcome") == "telegram.bot_text.admin.welcome"
    assert (
        _setting_key("reseller", "welcome", 7)
        == "telegram.bot_text.reseller.7.welcome"
    )
    assert (
        _setting_key("reseller", "welcome", 8)
        != _setting_key("reseller", "welcome", 7)
    )


def test_success_copy_changes_without_touching_dynamic_order_data():
    middleware = _middleware(
        "admin",
        {"purchase_success": "پرداخت انجام شد"},
    )
    source = (
        "✅ <b>پرداخت شما تأیید شد</b>\n\n"
        "🧾 سفارش: <b>#42</b>\n"
        "💰 مبلغ: <b>100,000 تومان</b>\n"
        "👤 نام کاربری: <code>mv42_7</code>"
    )

    result = middleware._rewrite(source)

    assert "✅ <b>پرداخت انجام شد</b>" in result
    assert "#42" in result
    assert "100,000 تومان" in result
    assert "mv42_7" in result


def test_custom_copy_is_html_escaped_before_telegram_parse_mode():
    middleware = _middleware(
        "admin",
        {"payment_rejected": "<script>bad</script>"},
    )

    result = middleware._rewrite(
        "❌ <b>پرداخت تأیید نشد</b>\n\nدلیل:\nنامعتبر"
    )

    assert "<script>" not in result
    assert "&lt;script&gt;bad&lt;/script&gt;" in result
    assert "نامعتبر" in result


def test_receipt_prompt_changes_copy_only():
    middleware = _middleware(
        "reseller",
        {"receipt_request": "لطفاً تصویر رسید را ارسال کنید."},
    )
    source = (
        "شماره سفارش: <b>#91</b>\n"
        "مبلغ: <b>250,000 تومان</b>\n\n"
        "بعد از پرداخت، <b>کد پیگیری یا تصویر رسید</b> را همین‌جا ارسال کنید."
    )

    result = middleware._rewrite(source)

    assert "لطفاً تصویر رسید را ارسال کنید." in result
    assert "#91" in result
    assert "250,000 تومان" in result
