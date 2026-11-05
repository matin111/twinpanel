"""Regression checks for Saman bank SMS Arabic glyphs and safe amount extraction."""
from app.payment_service import normalize_sms, parse_sms_amount_toman


def test_saman_deposit_uses_arabic_yeh_and_rial():
    message = "بانك سامان\nواريز مبلغ  1,995,980ريال\nبه 1234-567-1234567-1\nمانده 9,990,000"
    assert normalize_sms(message).startswith("بانک سامان\nواریز")
    assert parse_sms_amount_toman(message) == 199598


def test_persian_bank_sms_still_parses():
    assert parse_sms_amount_toman("واریز ۷۰,۸۷۴ تومان\nمانده ۳۰۰,۰۰۰ تومان") == 70874


def test_balance_only_is_not_mistaken_for_deposit():
    assert parse_sms_amount_toman("بانك سامان\nمانده 9,990,000 ريال") is None


def test_arabic_digit_rial_and_zero_space():
    assert parse_sms_amount_toman("واريز مبلغ  ١,٩٩٥,٩٨٠ريال\nمانده ٩,٩٩٠,٠٠٠") == 199598
