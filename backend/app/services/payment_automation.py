from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Subscription
from ..payment_models import (
    PaymentIntent,
    PaymentSettings,
    PaymentSmsReaderDevice,
)
from ..runtime_settings_model import RuntimeSetting
from ..store_models import StoreOrder
from ..telegram_notify_service import queue_telegram_notification


KEY_AUTO_RATE = "payments.auto_rate_enabled"
KEY_CRYPTO_AUTO_VERIFY = "payments.crypto_auto_verify"
KEY_LIVE_RATE = "payments.live_usdt_toman"
KEY_LIVE_RATE_PROVIDER = "payments.live_rate_provider"
KEY_LIVE_RATE_UPDATED_AT = "payments.live_rate_updated_at"
KEY_LIVE_RATE_ERROR = "payments.live_rate_error"

NOBITEX_ORDERBOOK_URL = (
    "https://api.nobitex.ir/v3/orderbook/USDTIRT"
)
NOBITEX_STATS_URL = (
    "https://api.nobitex.ir/market/stats"
)

TRON_GRID_BASE = os.getenv(
    "TWINPANEL_TRONGRID_BASE",
    "https://api.trongrid.io",
).rstrip("/")
TRON_USDT_CONTRACT = os.getenv(
    "TWINPANEL_TRON_USDT_CONTRACT",
    "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj",
).strip()

BSC_RPC_URLS = [
    x.strip()
    for x in os.getenv(
        "TWINPANEL_BSC_RPC_URLS",
        (
            "https://bsc-dataseed.bnbchain.org,"
            "https://bsc-dataseed-public.bnbchain.org"
        ),
    ).split(",")
    if x.strip()
]
BSC_USDT_CONTRACT = os.getenv(
    "TWINPANEL_BSC_USDT_CONTRACT",
    "0x55d398326f99059fF775485246999027B3197955",
).strip().lower()
BSC_USDT_DECIMALS = 18
BSC_MIN_CONFIRMATIONS = max(
    1,
    int(
        os.getenv(
            "TWINPANEL_BSC_MIN_CONFIRMATIONS",
            "3",
        )
    ),
)

ERC20_TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa"
    "952ba7f163c4a11628f55a4df523b3ef"
)


def _runtime_get(
    db: Session,
    key: str,
    default: str = "",
) -> str:
    row = db.get(RuntimeSetting, key)
    if row is None:
        return default
    return str(row.setting_value or "")


def _runtime_set(
    db: Session,
    key: str,
    value: object,
) -> None:
    row = db.get(RuntimeSetting, key)

    if row is None:
        row = RuntimeSetting(
            setting_key=key,
            setting_value=str(value),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
        return

    row.setting_value = str(value)
    row.updated_at = datetime.utcnow()


def _as_bool(
    value: object,
    default: bool = False,
) -> bool:
    normalized = str(value or "").strip().lower()

    if normalized in {"1", "true", "yes", "on"}:
        return True

    if normalized in {"0", "false", "no", "off"}:
        return False

    return default


def automation_settings(db: Session) -> dict:
    cfg = db.get(PaymentSettings, 1)

    try:
        live_rate = int(
            _runtime_get(
                db,
                KEY_LIVE_RATE,
                str(
                    int(cfg.usdt_rate_toman or 0)
                    if cfg
                    else 0
                ),
            )
            or 0
        )
    except Exception:
        live_rate = int(
            cfg.usdt_rate_toman or 0
        ) if cfg else 0

    return {
        "auto_rate_enabled": _as_bool(
            _runtime_get(db, KEY_AUTO_RATE, "1"),
            True,
        ),
        "crypto_auto_verify": _as_bool(
            _runtime_get(
                db,
                KEY_CRYPTO_AUTO_VERIFY,
                "1",
            ),
            True,
        ),
        "live_rate_toman": live_rate,
        "live_rate_provider": _runtime_get(
            db,
            KEY_LIVE_RATE_PROVIDER,
            "",
        ),
        "live_rate_updated_at": _runtime_get(
            db,
            KEY_LIVE_RATE_UPDATED_AT,
            "",
        ) or None,
        "live_rate_error": _runtime_get(
            db,
            KEY_LIVE_RATE_ERROR,
            "",
        ) or None,
    }


def set_automation_settings(
    db: Session,
    *,
    auto_rate_enabled: bool | None = None,
    crypto_auto_verify: bool | None = None,
) -> dict:
    if auto_rate_enabled is not None:
        _runtime_set(
            db,
            KEY_AUTO_RATE,
            "1" if auto_rate_enabled else "0",
        )

    if crypto_auto_verify is not None:
        _runtime_set(
            db,
            KEY_CRYPTO_AUTO_VERIFY,
            "1" if crypto_auto_verify else "0",
        )

    db.commit()
    return automation_settings(db)


def activate_existing_sms_auto_verify_once() -> dict:
    """Reuse an already-paired SMS Reader from the previous panel runtime.

    Auto verification is enabled only when an active device exists and the
    allowed-sender list is configured, so a clean install is never opened up
    accidentally.
    """

    db = SessionLocal()

    try:
        cfg = db.get(PaymentSettings, 1)
        if cfg is None:
            return {
                "ok": True,
                "changed": False,
                "reason": "settings_missing",
            }

        active_device = (
            db.query(PaymentSmsReaderDevice.id)
            .filter(
                PaymentSmsReaderDevice.active
                == True,
            )
            .first()
        )

        allowed = str(
            cfg.sms_allowed_senders or ""
        ).strip()

        if not active_device or not allowed:
            return {
                "ok": True,
                "changed": False,
                "reason": "reader_not_ready",
            }

        changed = False

        if not cfg.sms_reader_enabled:
            cfg.sms_reader_enabled = True
            changed = True

        if not cfg.sms_auto_verify:
            cfg.sms_auto_verify = True
            changed = True

        if changed:
            cfg.updated_at = datetime.utcnow()
            db.commit()

        return {
            "ok": True,
            "changed": changed,
            "device_id": int(active_device[0]),
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


async def _fetch_nobitex_orderbook_rate() -> tuple[int, str]:
    timeout = httpx.Timeout(
        8.0,
        connect=4.0,
    )

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
    ) as client:
        response = await client.get(
            NOBITEX_ORDERBOOK_URL,
            headers={
                "Accept": "application/json",
                "User-Agent": "TwinPanel/0.9.7",
            },
        )
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict):
        raise RuntimeError("invalid Nobitex response")

    asks = payload.get("asks") or []
    bids = payload.get("bids") or []

    ask = Decimal(str(asks[0][0])) if asks else None
    bid = Decimal(str(bids[0][0])) if bids else None

    if ask and bid and ask > 0 and bid > 0:
        rate = (ask + bid) / Decimal("2")
    else:
        latest = payload.get("lastTradePrice")
        rate = Decimal(str(latest or "0"))

    rounded = int(rate.quantize(Decimal("1")))

    if rounded < 1_000 or rounded > 100_000_000:
        raise RuntimeError("Nobitex USDTIRT rate out of range")

    return rounded, "nobitex:USDTIRT"


async def _fetch_nobitex_stats_rate() -> tuple[int, str]:
    timeout = httpx.Timeout(
        8.0,
        connect=4.0,
    )

    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
    ) as client:
        response = await client.get(
            NOBITEX_STATS_URL,
            params={
                "srcCurrency": "usdt",
                "dstCurrency": "rls",
            },
            headers={
                "Accept": "application/json",
                "User-Agent": "TwinPanel/0.9.7",
            },
        )
        response.raise_for_status()
        payload = response.json()

    stats = (
        payload.get("stats", {})
        if isinstance(payload, dict)
        else {}
    )
    row = stats.get("usdt-rls") or {}

    raw = (
        row.get("mark")
        or row.get("latest")
        or row.get("bestSell")
        or row.get("bestBuy")
        or 0
    )

    # RLS is Rial. TwinPanel prices are Toman.
    rate = Decimal(str(raw)) / Decimal("10")
    rounded = int(rate.quantize(Decimal("1")))

    if rounded < 1_000 or rounded > 100_000_000:
        raise RuntimeError("Nobitex USDT/RLS rate out of range")

    return rounded, "nobitex:USDT-RLS"


async def refresh_live_rate_once(
    *,
    force: bool = False,
) -> dict:
    db = SessionLocal()

    try:
        settings = automation_settings(db)

        if (
            not force
            and not settings["auto_rate_enabled"]
        ):
            return {
                "ok": True,
                "updated": False,
                "reason": "auto_rate_disabled",
                **settings,
            }

        errors: list[str] = []
        rate = 0
        provider = ""

        for fetcher in (
            _fetch_nobitex_orderbook_rate,
            _fetch_nobitex_stats_rate,
        ):
            try:
                rate, provider = await fetcher()
                break
            except Exception as exc:
                errors.append(str(exc)[:300])

        if rate <= 0:
            message = " | ".join(errors)[:900]
            _runtime_set(
                db,
                KEY_LIVE_RATE_ERROR,
                message,
            )
            db.commit()

            return {
                "ok": False,
                "updated": False,
                "error": message,
                **automation_settings(db),
            }

        cfg = db.get(PaymentSettings, 1)
        if cfg is None:
            cfg = PaymentSettings(id=1)
            db.add(cfg)
            db.flush()

        cfg.usdt_rate_toman = int(rate)
        cfg.updated_at = datetime.utcnow()

        now = datetime.utcnow().isoformat() + "Z"

        _runtime_set(db, KEY_LIVE_RATE, rate)
        _runtime_set(db, KEY_LIVE_RATE_PROVIDER, provider)
        _runtime_set(db, KEY_LIVE_RATE_UPDATED_AT, now)
        _runtime_set(db, KEY_LIVE_RATE_ERROR, "")

        db.commit()

        return {
            "ok": True,
            "updated": True,
            **automation_settings(db),
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def _normalize_bsc_txid(value: str) -> str | None:
    value = str(value or "").strip()
    if not value.startswith("0x"):
        value = "0x" + value

    if not re.fullmatch(
        r"0x[0-9a-fA-F]{64}",
        value,
    ):
        return None

    return value.lower()


def _normalize_bsc_address(value: str) -> str | None:
    value = str(value or "").strip()

    if not re.fullmatch(
        r"0x[0-9a-fA-F]{40}",
        value,
    ):
        return None

    return value.lower()


async def _verify_bep20_transfer(
    txid: str,
    destination: str,
) -> dict:
    normalized_txid = _normalize_bsc_txid(txid)
    normalized_destination = _normalize_bsc_address(
        destination
    )

    if normalized_txid is None:
        return {
            "state": "invalid",
            "reason": "invalid_bep20_txid",
        }

    if normalized_destination is None:
        return {
            "state": "invalid",
            "reason": "invalid_bep20_destination",
        }

    last_error = ""

    for rpc_url in BSC_RPC_URLS:
        try:
            timeout = httpx.Timeout(
                10.0,
                connect=4.0,
            )

            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "eth_getTransactionReceipt",
                        "params": [normalized_txid],
                        "id": 1,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                receipt = payload.get("result")

                if receipt is None:
                    return {
                        "state": "pending",
                        "reason": "transaction_not_mined",
                    }

                if str(receipt.get("status", "")).lower() != "0x1":
                    return {
                        "state": "invalid",
                        "reason": "transaction_failed",
                    }

                block_number = int(
                    str(receipt.get("blockNumber") or "0"),
                    16,
                )

                latest_response = await client.post(
                    rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "eth_blockNumber",
                        "params": [],
                        "id": 2,
                    },
                )
                latest_response.raise_for_status()
                latest_payload = latest_response.json()
                latest_block = int(
                    str(latest_payload.get("result") or "0"),
                    16,
                )

            confirmations = max(
                0,
                latest_block - block_number + 1,
            )

            if confirmations < BSC_MIN_CONFIRMATIONS:
                return {
                    "state": "pending",
                    "reason": "waiting_confirmations",
                    "confirmations": confirmations,
                    "required_confirmations":
                        BSC_MIN_CONFIRMATIONS,
                }

            for log in receipt.get("logs") or []:
                if (
                    str(log.get("address") or "").lower()
                    != BSC_USDT_CONTRACT
                ):
                    continue

                topics = log.get("topics") or []
                if (
                    len(topics) < 3
                    or str(topics[0]).lower()
                    != ERC20_TRANSFER_TOPIC
                ):
                    continue

                to_topic = str(topics[2] or "").lower()
                recipient = (
                    "0x" + to_topic[-40:]
                    if len(to_topic) >= 40
                    else ""
                )

                if recipient != normalized_destination:
                    continue

                raw_value = int(
                    str(log.get("data") or "0x0"),
                    16,
                )
                amount = (
                    Decimal(raw_value)
                    / (
                        Decimal(10)
                        ** BSC_USDT_DECIMALS
                    )
                )

                return {
                    "state": "confirmed",
                    "reason": "confirmed",
                    "amount": str(amount),
                    "confirmations": confirmations,
                    "network": "bep20",
                    "provider": rpc_url,
                }

            return {
                "state": "invalid",
                "reason": "usdt_transfer_to_wallet_not_found",
                "confirmations": confirmations,
            }

        except Exception as exc:
            last_error = str(exc)[:400]

    return {
        "state": "pending",
        "reason": "bsc_rpc_unavailable",
        "error": last_error,
    }


async def _verify_trc20_transfer(
    txid: str,
    destination: str,
    created_at: datetime | None,
) -> dict:
    normalized_txid = str(txid or "").strip().lower()
    destination = str(destination or "").strip()

    if not re.fullmatch(
        r"[0-9a-fA-F]{64}",
        normalized_txid,
    ):
        return {
            "state": "invalid",
            "reason": "invalid_trc20_txid",
        }

    if not destination:
        return {
            "state": "invalid",
            "reason": "invalid_trc20_destination",
        }

    headers = {
        "Accept": "application/json",
        "User-Agent": "TwinPanel/0.9.7",
    }

    tron_api_key = os.getenv(
        "TRON_PRO_API_KEY",
        "",
    ).strip()

    if tron_api_key:
        headers["TRON-PRO-API-KEY"] = tron_api_key

    min_timestamp = int(
        (
            (created_at or datetime.utcnow())
            - timedelta(hours=2)
        ).timestamp()
        * 1000
    )

    url = (
        f"{TRON_GRID_BASE}/v1/accounts/"
        f"{quote(destination, safe='')}/transactions/trc20"
    )

    try:
        timeout = httpx.Timeout(
            12.0,
            connect=5.0,
        )

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
        ) as client:
            response = await client.get(
                url,
                params={
                    "only_to": "true",
                    "only_confirmed": "true",
                    "contract_address":
                        TRON_USDT_CONTRACT,
                    "limit": 200,
                    "min_timestamp":
                        min_timestamp,
                },
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()

    except Exception as exc:
        return {
            "state": "pending",
            "reason": "trongrid_unavailable",
            "error": str(exc)[:400],
        }

    data = (
        payload.get("data") or []
        if isinstance(payload, dict)
        else []
    )

    for item in data:
        if (
            str(item.get("transaction_id") or "")
            .strip()
            .lower()
            != normalized_txid
        ):
            continue

        if (
            str(item.get("to") or "").strip()
            != destination
        ):
            return {
                "state": "invalid",
                "reason": "wrong_trc20_destination",
            }

        token = item.get("token_info") or {}
        try:
            decimals = int(token.get("decimals") or 6)
            raw_value = Decimal(
                str(item.get("value") or "0")
            )
            amount = (
                raw_value
                / (Decimal(10) ** decimals)
            )
        except (ValueError, InvalidOperation):
            return {
                "state": "invalid",
                "reason": "invalid_trc20_amount",
            }

        return {
            "state": "confirmed",
            "reason": "confirmed",
            "amount": str(amount),
            "network": "trc20",
            "provider": "trongrid",
            "block_timestamp":
                item.get("block_timestamp"),
        }

    return {
        "state": "pending",
        "reason": "transaction_not_confirmed",
    }


async def verify_crypto_intent(
    intent_id: int,
    db: Session,
) -> dict:
    settings = automation_settings(db)

    if not settings["crypto_auto_verify"]:
        return {
            "ok": True,
            "verified": False,
            "reason": "crypto_auto_verify_disabled",
        }

    intent = db.get(PaymentIntent, int(intent_id))

    if intent is None:
        return {
            "ok": False,
            "verified": False,
            "reason": "payment_not_found",
        }

    if intent.status in {
        "approved",
        "auto_verified",
        "paid",
    }:
        return {
            "ok": True,
            "verified": True,
            "reason": "already_verified",
        }

    method = str(intent.method or "").lower()

    if method not in {
        "usdt_trc20",
        "usdt_bep20",
    }:
        return {
            "ok": True,
            "verified": False,
            "reason": "not_crypto",
        }

    txid = str(intent.txid or "").strip()
    if not txid:
        return {
            "ok": True,
            "verified": False,
            "reason": "txid_missing",
        }

    cfg = db.get(PaymentSettings, 1)
    if cfg is None:
        return {
            "ok": False,
            "verified": False,
            "reason": "settings_missing",
        }

    destination = (
        str(cfg.usdt_trc20_address or "").strip()
        if method == "usdt_trc20"
        else str(cfg.usdt_bep20_address or "").strip()
    )

    if not destination:
        return {
            "ok": False,
            "verified": False,
            "reason": "wallet_not_configured",
        }

    if method == "usdt_trc20":
        chain_result = await _verify_trc20_transfer(
            txid,
            destination,
            intent.created_at,
        )
    else:
        chain_result = await _verify_bep20_transfer(
            txid,
            destination,
        )

    state = str(chain_result.get("state") or "pending")
    reason = str(chain_result.get("reason") or "unknown")

    if state != "confirmed":
        intent.review_note = (
            "auto-chain-check: "
            + reason
        )[:1000]
        db.commit()

        return {
            "ok": True,
            "verified": False,
            **chain_result,
        }

    try:
        received_amount = Decimal(
            str(chain_result.get("amount") or "0")
        )
        expected_amount = Decimal(
            str(intent.crypto_amount_usdt or "0")
        )
    except InvalidOperation:
        return {
            "ok": False,
            "verified": False,
            "reason": "invalid_expected_amount",
        }

    if expected_amount <= 0:
        return {
            "ok": False,
            "verified": False,
            "reason": "expected_amount_missing",
        }

    # Accept exact payment or an overpayment. Never auto-approve an
    # underpayment, even by a fraction of USDT.
    if received_amount < expected_amount:
        intent.review_note = (
            "auto-chain-check: amount_too_low "
            f"expected={expected_amount} "
            f"received={received_amount}"
        )[:1000]
        db.commit()

        return {
            "ok": True,
            "verified": False,
            "state": "invalid",
            "reason": "amount_too_low",
            "expected": str(expected_amount),
            "received": str(received_amount),
        }

    intent = (
        db.query(PaymentIntent)
        .filter(PaymentIntent.id == int(intent_id))
        .with_for_update()
        .first()
    )

    if intent is None:
        return {
            "ok": False,
            "verified": False,
            "reason": "payment_not_found",
        }

    if intent.status in {
        "approved",
        "auto_verified",
        "paid",
    }:
        return {
            "ok": True,
            "verified": True,
            "reason": "already_verified",
        }

    now = datetime.utcnow()
    intent.status = "auto_verified"
    intent.verified_at = now
    intent.review_note = (
        "auto-chain-verified: "
        f"{method} amount={received_amount}"
    )[:1000]

    order = db.get(StoreOrder, intent.order_id)

    if order is None:
        db.rollback()
        return {
            "ok": False,
            "verified": False,
            "reason": "order_missing",
        }

    order.status = "paid"
    order.payment_method = method
    order.payment_reference = txid
    if order.paid_at is None:
        order.paid_at = now

    db.commit()

    fulfilled = False
    fulfillment_error = None
    order_result = None

    try:
        from ..routers.store import _fulfill_paid_order

        order_result = await _fulfill_paid_order(
            order.id,
            db,
        )
        fulfilled = True

    except HTTPException as exc:
        fulfillment_error = exc.detail

    if fulfilled:
        try:
            final_order = db.get(StoreOrder, order.id)
            subscription_id = (
                final_order.subscription_id
                if final_order
                else None
            )
            subscription = (
                db.get(Subscription, subscription_id)
                if subscription_id
                else None
            )

            queue_telegram_notification(
                db,
                user_id=intent.user_id,
                event_key=(
                    f"payment-auto-approved:{intent.id}"
                ),
                kind="payment_approved",
                payload={
                    "payment_id": intent.id,
                    "order_id": order.id,
                    "subscription_id": subscription_id,
                    "username": (
                        subscription.account_username
                        if subscription
                        else None
                    ),
                    "amount_toman": int(
                        intent.base_amount_toman or 0
                    ),
                },
            )
            db.commit()

        except Exception as exc:
            db.rollback()
            print(
                "auto crypto telegram notification failed:",
                str(exc),
                flush=True,
            )

    return {
        "ok": True,
        "verified": True,
        "fulfilled": fulfilled,
        "fulfillment_error": fulfillment_error,
        "order": order_result,
        **chain_result,
    }


async def process_pending_crypto_payments_once(
    limit: int = 50,
) -> dict:
    lookup_db = SessionLocal()

    try:
        ids = [
            int(row[0])
            for row in (
                lookup_db.query(PaymentIntent.id)
                .filter(
                    PaymentIntent.method.in_(
                        ["usdt_trc20", "usdt_bep20"]
                    ),
                    PaymentIntent.txid.isnot(None),
                    PaymentIntent.status.in_(
                        ["awaiting_review", "payment_submitted"]
                    ),
                )
                .order_by(PaymentIntent.id.asc())
                .limit(max(1, min(int(limit), 200)))
                .all()
            )
        ]
    finally:
        lookup_db.close()

    checked = 0
    verified = 0
    errors = 0

    for intent_id in ids:
        db = SessionLocal()

        try:
            result = await verify_crypto_intent(
                intent_id,
                db,
            )
            checked += 1
            if result.get("verified"):
                verified += 1

        except Exception as exc:
            errors += 1
            db.rollback()
            print(
                "crypto payment auto verification failed:",
                intent_id,
                str(exc),
                flush=True,
            )

        finally:
            db.close()

    return {
        "ok": errors == 0,
        "checked": checked,
        "verified": verified,
        "errors": errors,
    }
