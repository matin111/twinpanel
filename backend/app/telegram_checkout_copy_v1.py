"""One compact, consistent Telegram checkout copy for purchase and renewal."""
from html import escape


def operation(renewal=False):
    return "تمدید" if renewal else "خرید"


def choose_payment_text(order_id=None, amount=None, renewal=False):
    title = f"💳 <b>پرداخت {operation(renewal)}</b>"
    details = ""
    if order_id is not None:
        details += f"\n🧾 سفارش: <b>#{int(order_id)}</b>"
    if amount is not None:
        details += f"\n💰 مبلغ: <b>{int(amount or 0):,} تومان</b>"
    return title + details + "\n\nروش پرداخت را انتخاب کنید."


def method_label(method):
    method_id = str(method.get("id") or "")
    title = str(method.get("title") or method_id).strip()
    return ("💳 " if method_id == "card_to_card" else "🪙 ") + title


def payment_detail_text(method_id, method, intent, renewal=False):
    title = escape(str(method.get("title") or method_id))
    payable = int(intent.get("payable_amount_toman") or 0)
    text = (f"💳 <b>پرداخت {operation(renewal)} | {title}</b>\n\n"
            f"💰 مبلغ: <b>{payable:,} تومان</b>\n")
    if method_id == "card_to_card":
        text += (
            "\n💳 شماره کارت:\n"
            f"<code>{escape(str(method.get('card_number') or '-'))}</code>\n"
            f"👤 صاحب کارت: <b>{escape(str(method.get('card_holder') or '-'))}</b>\n"
            "\nپس از واریز، تصویر رسید را ارسال کنید."
        )
    else:
        text += (
            "\n🔗 آدرس کیف پول:\n"
            f"<code>{escape(str(method.get('address') or '-'))}</code>\n"
        )
        if intent.get("crypto_amount_usdt"):
            text += (
                f"🪙 مقدار: <b>{escape(str(intent['crypto_amount_usdt']))} USDT</b>\n"
            )
        text += "\nپس از انتقال، هش تراکنش (TXID) را ثبت کنید."
    return text


def proof_prompt(method_id, renewal=False):
    if method_id == "card_to_card":
        return ("📷 <b>ارسال رسید پرداخت</b>\n\n"
                "عکس رسید یا فایل PDF را ارسال کنید.")
    return ("🔗 <b>ثبت هش تراکنش (TXID)</b>\n\n"
            "هش انتقال را از تاریخچه کیف پول کپی و ارسال کنید.")


def proof_success(status=None, renewal=False, receipt=False):
    title = "رسید پرداخت" if receipt else "هش تراکنش"
    text = f"✅ <b>{title} ثبت شد</b>\n"
    if status:
        text += f"\nوضعیت: <b>{escape(str(status))}</b>\n"
    text += (f"\nپس از تأیید، {operation(renewal)} "
             + ("برای دوره بعد رزرو می‌شود و پس از پایان زمان یا حجم دوره فعلی، خودکار فعال می‌شود." if renewal else "به‌صورت خودکار تکمیل می‌شود."))
    return text


def wallet_preview_text(order_id, amount, balance, renewal=False):
    sufficient = balance >= amount
    text = (
        f"💰 <b>پرداخت {operation(renewal)} از کیف پول</b>\n\n"
        f"🧾 سفارش: <b>#{int(order_id)}</b>\n"
        f"💵 مبلغ: <b>{int(amount):,} تومان</b>\n"
        f"💰 موجودی: <b>{int(balance):,} تومان</b>\n"
    )
    if sufficient:
        text += (f"✅ مانده: <b>{int(balance-amount):,} تومان</b>\n\n"
                 "برای پرداخت تأیید کنید.")
    else:
        text += "\n❌ موجودی کافی نیست؛ کیف پول را شارژ کنید."
    return text



def wallet_success_text(order_id, renewal=False, fulfilled=False):
    text = (
        f"✅ <b>پرداخت {operation(renewal)} ثبت شد</b>\n\n"
        f"🧾 سفارش: <b>#{int(order_id)}</b>\n"
        "💰 مبلغ از کیف پول پرداخت شد.\n"
    )
    if renewal:
        text += "🕒 تمدید برای دوره بعد رزرو شد و پس از پایان زمان یا حجم دوره فعلی، خودکار فعال می‌شود."
    elif fulfilled:
        text += "📦 اشتراک شما آماده است."
    else:
        text += "📦 اشتراک در حال آماده‌سازی است."
    return text
