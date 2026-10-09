import hashlib
import hmac
import re
import time

from fastapi import HTTPException

from .config import settings


_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


def normalize_sms(value: str) -> str:
    value = str(value or "").translate(_DIGITS)
    value = value.replace("٬", ",")
    return value


def parse_sms_amount_toman(
    message: str,
) -> int | None:
    text = normalize_sms(message)

    matches = list(
        re.finditer(
            r"(\d[\d,\s]{2,20})\s*"
            r"(تومان|تومن|ریال)",
            text,
            re.IGNORECASE,
        )
    )

    candidates = []

    for match in matches:
        raw = re.sub(
            r"[^\d]",
            "",
            match.group(1),
        )

        if not raw:
            continue

        value = int(raw)

        if value <= 0:
            continue

        currency = match.group(2)

        if currency == "ریال":
            value = int(round(value / 10))

        start = max(0, match.start() - 45)
        end = min(
            len(text),
            match.end() + 45,
        )

        around = text[start:end].lower()

        score = 0

        positive = (
            "واریز",
            "واریزی",
            "بستانکار",
            "افزایش",
            "deposit",
            "credited",
            "credit",
        )

        negative = (
            "مانده",
            "موجودی",
            "balance",
        )

        if any(x in around for x in positive):
            score += 5

        if any(x in around for x in negative):
            score -= 4

        candidates.append(
            (score, value)
        )

    if not candidates:
        # TWINPANEL_SMS_READER_PASARGAD_PLUS_V1
        # Pasargad SMS Reader example:
        #
        # +1,995,980
        #
        # Pasargad sends this amount in Rial while
        # PaymentIntent payable_amount_toman is Toman.
        for line in text.splitlines():
            line = line.strip()

            if not line.startswith("+"):
                continue

            found = re.findall(
                r"[0-9][0-9,\.]*",
                line,
            )

            for raw in found:
                digits = re.sub(
                    r"[^\d]",
                    "",
                    raw,
                )

                if not digits:
                    continue

                value = int(digits)

                if value < 10_000:
                    continue

                if value % 10 == 0:
                    return value // 10

                return value

        return None

    candidates.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    if candidates[0][0] <= 0:
        return None

    return candidates[0][1]


def verify_sms_signature(
    raw_body: bytes,
    timestamp: str,
    nonce: str,
    signature: str,
):
    secret = (
        settings.payment_sms_relay_secret
        or ""
    ).strip()

    if not secret:
        raise HTTPException(
            status_code=503,
            detail="SMS relay secret is not configured",
        )

    try:
        ts = int(timestamp)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="invalid timestamp",
        )

    if abs(int(time.time()) - ts) > 300:
        raise HTTPException(
            status_code=401,
            detail="expired request",
        )

    if not nonce or len(nonce) > 100:
        raise HTTPException(
            status_code=401,
            detail="invalid nonce",
        )

    signed = (
        timestamp.encode()
        + b"\n"
        + nonce.encode()
        + b"\n"
        + raw_body
    )

    expected = hmac.new(
        secret.encode(),
        signed,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(
        expected,
        str(signature or "").lower(),
    ):
        raise HTTPException(
            status_code=401,
            detail="invalid signature",
        )
