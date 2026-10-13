from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode, urlsplit

import httpx

from ..database import SessionLocal
from ..payment_models import PaymentSettings, PaymentSmsReaderDevice
from ..runtime_settings_model import RuntimeSetting


KEY_AUTO_RATE = "payments.auto_rate_enabled"
KEY_CRYPTO_AUTO_VERIFY = "payments.crypto_auto_verify"
KEY_LIVE_RATE = "payments.live_usdt_toman"
KEY_LIVE_RATE_PROVIDER = "payments.live_rate_provider"
KEY_LIVE_RATE_UPDATED_AT = "payments.live_rate_updated_at"
KEY_LIVE_RATE_ERROR = "payments.live_rate_error"
KEY_MARKET_RATES = "payments.market_rates_v2"

RATE_SYMBOLS = ("USDT", "TRX", "BNB")
REFRESH_SECONDS = 15


def _runtime_get(db, key: str, default: str = "") -> str:
    row = db.get(RuntimeSetting, key)
    if row is None:
        return default
    return str(row.setting_value or "")


def _runtime_set(db, key: str, value: object) -> None:
    row = db.get(RuntimeSetting, key)
    text = value if isinstance(value, str) else str(value)

    if row is None:
        db.add(
            RuntimeSetting(
                setting_key=key,
                setting_value=text,
                updated_at=datetime.utcnow(),
            )
        )
        return

    row.setting_value = text
    row.updated_at = datetime.utcnow()


def _load_snapshot(db) -> dict:
    raw = _runtime_get(db, KEY_MARKET_RATES, "")

    if raw:
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass

    cfg = db.get(PaymentSettings, 1)
    usdt = int(cfg.usdt_rate_toman or 0) if cfg else 0

    return {
        "ok": bool(usdt),
        "updated_at": None,
        "rates": {
            "USDT": {
                "symbol": "USDT",
                "rate_toman": usdt,
                "provider": "stored" if usdt else None,
                "updated_at": None,
                "error": None,
            },
            "TRX": {
                "symbol": "TRX",
                "rate_toman": 0,
                "provider": None,
                "updated_at": None,
                "error": None,
            },
            "BNB": {
                "symbol": "BNB",
                "rate_toman": 0,
                "provider": None,
                "updated_at": None,
                "error": None,
            },
        },
    }


def market_snapshot() -> dict:
    db = SessionLocal()
    try:
        return _load_snapshot(db)
    finally:
        db.close()


def _resolve_with_doh(host: str) -> list[str]:
    providers = (
        (
            "cloudflare-dns.com",
            "1.1.1.1",
            f"https://cloudflare-dns.com/dns-query?name={host}&type=A",
            ["-H", "Accept: application/dns-json"],
        ),
        (
            "dns.google",
            "8.8.8.8",
            f"https://dns.google/resolve?name={host}&type=A",
            [],
        ),
    )

    for doh_host, doh_ip, url, extra in providers:
        try:
            proc = subprocess.run(
                [
                    "curl",
                    "-fsS",
                    "--max-time",
                    "6",
                    "--resolve",
                    f"{doh_host}:443:{doh_ip}",
                    *extra,
                    url,
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            if proc.returncode != 0:
                continue

            payload = json.loads(proc.stdout)
            answers = payload.get("Answer") or []
            ips = []

            for item in answers:
                if int(item.get("type") or 0) != 1:
                    continue
                value = str(item.get("data") or "").strip()
                if value and value not in ips:
                    ips.append(value)

            if ips:
                return ips

        except Exception:
            continue

    return []


def _curl_json_with_resolve(url: str, params: dict | None = None) -> dict:
    parsed = urlsplit(url)
    host = parsed.hostname or ""

    if not host:
        raise RuntimeError("invalid provider host")

    target = url
    if params:
        query = urlencode(params)
        target += ("&" if "?" in target else "?") + query

    ips = _resolve_with_doh(host)

    if not ips:
        raise RuntimeError(f"DNS fallback failed for {host}")

    errors = []

    for ip in ips[:3]:
        proc = subprocess.run(
            [
                "curl",
                "-fsS",
                "--max-time",
                "8",
                "--resolve",
                f"{host}:443:{ip}",
                "-H",
                "Accept: application/json",
                "-H",
                "User-Agent: TwinPanel/0.9.7",
                target,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        if proc.returncode == 0:
            payload = json.loads(proc.stdout)
            if isinstance(payload, dict):
                return payload

        errors.append(proc.stderr.strip()[:200])

    raise RuntimeError("curl provider fallback failed: " + " | ".join(errors))


async def _get_json(url: str, params: dict | None = None) -> dict:
    try:
        timeout = httpx.Timeout(8.0, connect=4.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            response = await client.get(
                url,
                params=params,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "TwinPanel/0.9.7",
                },
            )
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, dict):
            raise RuntimeError("provider returned non-object JSON")

        return payload

    except Exception as first_error:
        try:
            return await asyncio.to_thread(
                _curl_json_with_resolve,
                url,
                params,
            )
        except Exception as fallback_error:
            raise RuntimeError(
                f"{first_error} | {fallback_error}"
            ) from fallback_error


def _midpoint(ask: Decimal | None, bid: Decimal | None) -> Decimal:
    if ask is not None and bid is not None and ask > 0 and bid > 0:
        return (ask + bid) / Decimal("2")
    if ask is not None and ask > 0:
        return ask
    if bid is not None and bid > 0:
        return bid
    return Decimal("0")


def _validate_rate(symbol: str, value: int) -> int:
    limits = {
        "USDT": (1_000, 10_000_000),
        "TRX": (1, 100_000_000),
        "BNB": (1_000, 10_000_000_000),
    }

    low, high = limits[symbol]

    if not low <= int(value) <= high:
        raise RuntimeError(f"{symbol} rate out of range: {value}")

    return int(value)


async def _nobitex_rate(symbol: str, host: str) -> tuple[int, str]:
    market = f"{symbol}IRT"
    payload = await _get_json(
        f"https://{host}/v3/orderbook/{market}"
    )

    if str(payload.get("status") or "ok").lower() not in {"ok", "success"}:
        raise RuntimeError(f"Nobitex rejected {market}")

    latest = Decimal(str(payload.get("lastTradePrice") or "0"))

    if latest <= 0:
        asks = payload.get("asks") or []
        bids = payload.get("bids") or []
        ask = Decimal(str(asks[0][0])) if asks else None
        bid = Decimal(str(bids[0][0])) if bids else None
        latest = _midpoint(ask, bid)

    value = _validate_rate(
        symbol,
        int(latest.quantize(Decimal("1"))),
    )

    return value, f"nobitex:{host}:{market}"


async def _wallex_rate(symbol: str) -> tuple[int, str]:
    market = f"{symbol}TMN"
    payload = await _get_json(
        "https://api.wallex.ir/v1/depth",
        {"symbol": market},
    )

    result = payload.get("result") or {}
    asks = result.get("ask") or []
    bids = result.get("bid") or []

    ask = Decimal(str(asks[0].get("price"))) if asks else None
    bid = Decimal(str(bids[0].get("price"))) if bids else None
    value = _midpoint(ask, bid)

    rate = _validate_rate(
        symbol,
        int(value.quantize(Decimal("1"))),
    )

    return rate, f"wallex:{market}"


async def _fetch_symbol(symbol: str) -> tuple[int, str, list[str]]:
    errors: list[str] = []

    providers = (
        lambda: _nobitex_rate(symbol, "apiv2.nobitex.ir"),
        lambda: _nobitex_rate(symbol, "api.nobitex.ir"),
        lambda: _wallex_rate(symbol),
    )

    for provider in providers:
        try:
            rate, source = await provider()
            return rate, source, errors
        except Exception as exc:
            errors.append(str(exc)[:350])

    return 0, "", errors


def ensure_requested_payment_automation_once() -> dict:
    db = SessionLocal()

    try:
        cfg = db.get(PaymentSettings, 1)
        if cfg is None:
            cfg = PaymentSettings(id=1)
            db.add(cfg)
            db.flush()

        changed = False

        if not cfg.sms_reader_enabled:
            cfg.sms_reader_enabled = True
            changed = True

        if not cfg.sms_auto_verify:
            cfg.sms_auto_verify = True
            changed = True

        # Restore the same sender used by the proven previous setup only when
        # migration left the field empty. Admin can still edit it afterwards.
        if not str(cfg.sms_allowed_senders or "").strip():
            cfg.sms_allowed_senders = "B.Pasargad"
            changed = True

        if int(cfg.unique_amount_max_extra or 0) <= 0:
            cfg.unique_amount_max_extra = 900
            changed = True

        _runtime_set(db, KEY_AUTO_RATE, "1")
        _runtime_set(db, KEY_CRYPTO_AUTO_VERIFY, "1")

        if changed:
            cfg.updated_at = datetime.utcnow()

        active_readers = (
            db.query(PaymentSmsReaderDevice.id)
            .filter(
                PaymentSmsReaderDevice.active == True,
                PaymentSmsReaderDevice.revoked_at == None,
            )
            .count()
        )

        db.commit()

        return {
            "ok": True,
            "changed": changed,
            "sms_reader_enabled": bool(cfg.sms_reader_enabled),
            "sms_auto_verify": bool(cfg.sms_auto_verify),
            "allowed_senders": str(cfg.sms_allowed_senders or ""),
            "active_readers": int(active_readers),
            "card_auto_verify_operational": bool(
                cfg.sms_reader_enabled
                and cfg.sms_auto_verify
                and active_readers > 0
                and str(cfg.sms_allowed_senders or "").strip()
            ),
            "crypto_auto_verify": True,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


async def refresh_market_rates_once(*, force: bool = False) -> dict:
    db = SessionLocal()

    try:
        if not force and _runtime_get(db, KEY_AUTO_RATE, "1") != "1":
            return {
                **_load_snapshot(db),
                "updated": False,
                "reason": "auto_rate_disabled",
            }

        previous = _load_snapshot(db)
        previous_rates = previous.get("rates") or {}
        now = datetime.utcnow().isoformat() + "Z"
        rates: dict[str, dict] = {}
        success_count = 0

        for symbol in RATE_SYMBOLS:
            rate, provider, errors = await _fetch_symbol(symbol)

            if rate > 0:
                success_count += 1
                rates[symbol] = {
                    "symbol": symbol,
                    "rate_toman": int(rate),
                    "provider": provider,
                    "updated_at": now,
                    "error": None,
                }
            else:
                old = previous_rates.get(symbol) or {}
                rates[symbol] = {
                    "symbol": symbol,
                    "rate_toman": int(old.get("rate_toman") or 0),
                    "provider": old.get("provider"),
                    "updated_at": old.get("updated_at"),
                    "error": " | ".join(errors)[-1200:] or "all providers failed",
                }

        snapshot = {
            "ok": success_count > 0,
            "updated": success_count > 0,
            "updated_at": now if success_count else previous.get("updated_at"),
            "rates": rates,
        }

        _runtime_set(
            db,
            KEY_MARKET_RATES,
            json.dumps(snapshot, ensure_ascii=False),
        )

        usdt = rates.get("USDT") or {}
        usdt_rate = int(usdt.get("rate_toman") or 0)

        if usdt_rate > 0:
            cfg = db.get(PaymentSettings, 1)
            if cfg is None:
                cfg = PaymentSettings(id=1)
                db.add(cfg)
                db.flush()

            cfg.usdt_rate_toman = usdt_rate
            cfg.updated_at = datetime.utcnow()

            _runtime_set(db, KEY_LIVE_RATE, usdt_rate)
            _runtime_set(db, KEY_LIVE_RATE_PROVIDER, usdt.get("provider") or "")
            _runtime_set(db, KEY_LIVE_RATE_UPDATED_AT, usdt.get("updated_at") or now)
            _runtime_set(db, KEY_LIVE_RATE_ERROR, usdt.get("error") or "")

        db.commit()
        return snapshot

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


async def payment_market_loop() -> None:
    try:
        activated = await asyncio.to_thread(
            ensure_requested_payment_automation_once
        )
        print(
            "PAYMENT_AUTOMATION_V2_READY",
            activated,
            flush=True,
        )
    except Exception as exc:
        print(
            "payment automation v2 activation failed:",
            str(exc),
            flush=True,
        )

    while True:
        try:
            result = await refresh_market_rates_once()
            compact = {
                key: int((result.get("rates") or {}).get(key, {}).get("rate_toman") or 0)
                for key in RATE_SYMBOLS
            }
            print(
                "PAYMENT_MARKET_RATES_UPDATED",
                compact,
                flush=True,
            )
        except Exception as exc:
            print(
                "payment market rate loop failed:",
                str(exc),
                flush=True,
            )

        await asyncio.sleep(REFRESH_SECONDS)
