from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / "backend/app/routers/admin_panel_notifications.py"
UI = ROOT / "components/admin-notification-center.tsx"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_admin_notification_feed_syncs_both_transaction_types():
    source = _source(ROUTER)

    assert "TWINPANEL_ADMIN_PANEL_NOTIFICATION_API_V3" in source
    assert "PaymentIntent" in source
    assert "CustomerWalletTopup" in source
    assert 'f"payment-intent:{int(row.id)}"' in source
    assert 'f"wallet-topup:{int(row.id)}"' in source
    assert 'notification.source = "payment"' in source
    assert 'notification.category = "payment"' in source
    assert 'notification.route = "payments"' in source


def test_transaction_notifications_contain_admin_useful_context():
    source = _source(ROUTER)

    assert "تراکنش خرید اشتراک" in source
    assert "تراکنش شارژ کیف پول" in source
    assert "مبلغ:" in source
    assert "روش:" in source
    assert "وضعیت:" in source
    assert "شناسه پرداخت:" in source
    assert "شناسه سفارش:" in source
    assert "شناسه تراکنش:" in source


def test_reseller_transactions_remain_isolated_from_central_admin():
    source = _source(ROUTER)

    assert 'RESELLER_TOPUP_METHOD_PATTERN = "reseller_card:%"' in source
    assert 'RESELLER_INTERNAL_EMAIL_SUFFIX = "@internal.twinpanel.invalid"' in source
    assert "_is_reseller_internal_user" in source
    assert "~CustomerWalletTopup.method.like(" in source


def test_admin_dropdown_already_supports_payment_source_and_payments_route():
    source = _source(UI)

    assert 'source==="payment"||category==="payment"' in source
    assert 'return `/admin/${route.replace(/^admin\\//,"")}`' in source
    assert "opsApi.panelNotifications()" in source
    assert 'playNotificationSound("receipt")' in source
