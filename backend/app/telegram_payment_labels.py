"""Human-readable payment verification labels for Telegram notifications.

The verified payment status is the source of truth, not the notification event key:
legacy event-key normalization deliberately combines manual/automatic keys.
"""


def payment_approved_heading(payment_status: str | None) -> str:
    """Show the actual verification method without changing payment accounting."""
    status = str(payment_status or "").strip().lower()
    if status == "auto_verified":
        return "✅ <b>پرداخت شما به‌صورت خودکار تأیید شد</b>"
    if status == "approved":
        return "✅ <b>پرداخت شما به‌صورت دستی تأیید شد</b>"
    return "✅ <b>پرداخت شما تأیید شد</b>"
