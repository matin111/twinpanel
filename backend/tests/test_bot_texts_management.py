from app.bot_text_middleware import BotTextRequestMiddleware
from app.bot_texts import _install_main_runtime_service_override, _setting_key
from app.routers import runtime_endpoints, telegram_manager


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


def test_admin_and_reseller_text_routes_are_registered():
    paths = {route.path for route in runtime_endpoints.router.routes}

    assert "/v1/admin/telegram-bot/texts" in paths
    assert "/v1/admin/telegram-bot/texts/reset" in paths
    assert "/v1/reseller/bot/texts" in paths
    assert "/v1/reseller/bot/texts/reset" in paths


def test_main_bot_service_uses_text_aware_runtime():
    # bot_texts intentionally tolerates an early circular/import-time failure.
    # Re-apply the idempotent override after router imports are complete so the
    # test validates the production repair path instead of Python import order.
    _install_main_runtime_service_override()
    service_text = telegram_manager._service_text()

    assert "-m app.telegram_runtime_custom" in service_text
    assert "-m app.telegram_runtime_bot\n" not in service_text


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


def test_pending_review_copy_does_not_remove_receipt_id():
    middleware = _middleware(
        "admin",
        {"awaiting_approval": "در انتظار تأیید ادمین"},
    )
    source = (
        "✅ <b>رسید پرداخت ثبت شد</b>\n\n"
        "شناسه پرداخت: <b>#77</b>\n"
        "وضعیت: <b>در انتظار بررسی</b>"
    )

    result = middleware._rewrite(source)

    assert "در انتظار تأیید ادمین" in result
    assert "#77" in result
