from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Subscription
from ..payment_models import PaymentIntent
from ..runtime_settings_model import RuntimeSetting
from ..store_models import StoreOrder
from ..telegram_notify_service import queue_telegram_notification


KEY_TRX_ENABLED = "payments.trx_tron_enabled"
KEY_TRX_ADDRESS = "payments.trx_tron_address"
KEY_BNB_ENABLED = "payments.bnb_bsc_enabled"
KEY_BNB_ADDRESS = "payments.bnb_bsc_address"
KEY_CRYPTO_AUTO_VERIFY = "payments.crypto_auto_verify"

TRON_GRID_BASE = os.getenv(
    "TWINPANEL_TRONGRID_BASE",
    "https://api.trongrid.io",
).rstrip("/")

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

BSC_MIN_CONFIRMATIONS = max(
    1,
    int(os.getenv("TWINPANEL_BSC_MIN_CONFIRMATIONS", "3")),
)

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BASE58_MAP = {char: index for index, char in enumerate(_BASE58_ALPHABET)}


def _runtime_get(db: Session, key: str, default: str = "") -> str:
    row = db.get(RuntimeSetting, key)
    if row is None:
        return default
    return str(row.setting_value or "")


def _runtime_set(db: Session, key: str, value: object) -> None:
    row = db.get(RuntimeSetting, key)
    text = str(value)

    if row is None:
        db.add(RuntimeSetting(
            setting_key=key,
            setting_value=text,
            updated_at=datetime.utcnow(),
        ))
        return

    row.setting_value = text
    row.updated_at = datetime.utcnow()


def _as_bool(value: object, default: bool = False) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def native_gateway_settings(db: Session) -> dict:
    return {
        "trx_tron_enabled": _as_bool(_runtime_get(db, KEY_TRX_ENABLED, "0")),
        "trx_tron_address": _runtime_get(db, KEY_TRX_ADDRESS, "").strip(),
        "bnb_bsc_enabled": _as_bool(_runtime_get(db, KEY_BNB_ENABLED, "0")),
        "bnb_bsc_address": _runtime_get(db, KEY_BNB_ADDRESS, "").strip(),
    }


def update_native_gateway_settings(
    db: Session,
    *,
    trx_tron_enabled: bool | None = None,
    trx_tron_address: str | None = None,
    bnb_bsc_enabled: bool | None = None,
    bnb_bsc_address: str | None = None,
) -> dict:
    if trx_tron_enabled is not None:
        _runtime_set(db, KEY_TRX_ENABLED, "1" if trx_tron_enabled else "0")
    if trx_tron_address is not None:
        _runtime_set(db, KEY_TRX_ADDRESS, str(trx_tron_address or "").strip())
    if bnb_bsc_enabled is not None:
        _runtime_set(db, KEY_BNB_ENABLED, "1" if bnb_bsc_enabled else "0")
    if bnb_bsc_address is not None:
        _runtime_set(db, KEY_BNB_ADDRESS, str(bnb_bsc_address or "").strip())

    db.commit()
    return native_gateway_settings(db)


def _crypto_auto_verify_enabled(db: Session) -> bool:
    return _as_bool(_runtime_get(db, KEY_CRYPTO_AUTO_VERIFY, "1"), True)


def _decode_tron_base58check(address: str) -> str | None:
    value = str(address or "").strip()
    if not value or any(char not in _BASE58_MAP for char in value):
        return None

    number = 0
    for char in value:
        number = number * 58 + _BASE58_MAP[char]

    payload = number.to_bytes(max(1, (number.bit_length() + 7) // 8), "big")
    leading_zeroes = len(value) - len(value.lstrip("1"))
    payload = (b"\x00" * leading_zeroes) + payload

    if len(payload) != 25:
        return None

    body = payload[:21]
    checksum = payload[21:]
    expected = hashlib.sha256(hashlib.sha256(body).digest()).digest()[:4]

    if checksum != expected or body[0] != 0x41:
        return None

    return body.hex().upper()


async def _verify_trx(txid: str, destination: str) -> dict:
    txid = str(txid or "").strip().lower()
    destination_hex = _decode_tron_base58check(destination)

    if not re.fullmatch(r"[0-9a-fA-F]{64}", txid):
        return {"state": "invalid", "reason": "invalid_trx_txid"}
    if destination_hex is None:
        return {"state": "invalid", "reason": "invalid_tron_destination"}

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "TwinPanel/0.9.7",
    }
    tron_key = os.getenv("TRON_PRO_API_KEY", "").strip()
    if tron_key:
        headers["TRON-PRO-API-KEY"] = tron_key

    try:
        timeout = httpx.Timeout(12.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.post(
                f"{TRON_GRID_BASE}/walletsolidity/gettransactionbyid",
                json={"value": txid},
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        return {"state": "pending", "reason": "trongrid_unavailable", "error": str(exc)[:400]}

    if not isinstance(payload, dict) or not payload.get("txID"):
        return {"state": "pending", "reason": "transaction_not_confirmed"}

    ret = payload.get("ret") or []
    if ret and str(ret[0].get("contractRet") or "").upper() != "SUCCESS":
        return {"state": "invalid", "reason": "trx_transaction_failed"}

    for contract in ((payload.get("raw_data") or {}).get("contract") or []):
        if str(contract.get("type") or "") != "TransferContract":
            continue

        value = ((contract.get("parameter") or {}).get("value") or {})
        if str(value.get("to_address") or "").upper() != destination_hex:
            continue

        try:
            amount = Decimal(str(value.get("amount") or "0")) / Decimal("1000000")
        except InvalidOperation:
            return {"state": "invalid", "reason": "invalid_trx_amount"}

        if amount <= 0:
            return {"state": "invalid", "reason": "invalid_trx_amount"}

        return {
            "state": "confirmed",
            "reason": "confirmed",
            "amount": str(amount),
            "asset": "TRX",
            "network": "tron",
            "provider": "trongrid:walletsolidity",
        }

    return {"state": "invalid", "reason": "trx_transfer_to_wallet_not_found"}


async def _verify_bnb(txid: str, destination: str) -> dict:
    txid = str(txid or "").strip()
    if not txid.startswith("0x"):
        txid = "0x" + txid

    destination = str(destination or "").strip().lower()

    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", txid):
        return {"state": "invalid", "reason": "invalid_bnb_txid"}
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", destination):
        return {"state": "invalid", "reason": "invalid_bnb_destination"}

    last_error = ""

    for rpc_url in BSC_RPC_URLS:
        try:
            timeout = httpx.Timeout(10.0, connect=4.0)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                tx_response = await client.post(rpc_url, json={
                    "jsonrpc": "2.0",
                    "method": "eth_getTransactionByHash",
                    "params": [txid.lower()],
                    "id": 1,
                })
                tx_response.raise_for_status()
                tx = tx_response.json().get("result")

                if tx is None:
                    return {"state": "pending", "reason": "transaction_not_mined"}

                receipt_response = await client.post(rpc_url, json={
                    "jsonrpc": "2.0",
                    "method": "eth_getTransactionReceipt",
                    "params": [txid.lower()],
                    "id": 2,
                })
                receipt_response.raise_for_status()
                receipt = receipt_response.json().get("result")

                if receipt is None:
                    return {"state": "pending", "reason": "transaction_not_mined"}
                if str(receipt.get("status") or "").lower() != "0x1":
                    return {"state": "invalid", "reason": "transaction_failed"}

                if str(tx.get("to") or "").lower() != destination:
                    return {"state": "invalid", "reason": "wrong_bnb_destination"}

                raw_value = int(str(tx.get("value") or "0x0"), 16)
                amount = Decimal(raw_value) / (Decimal(10) ** 18)

                latest_response = await client.post(rpc_url, json={
                    "jsonrpc": "2.0",
                    "method": "eth_blockNumber",
                    "params": [],
                    "id": 3,
                })
                latest_response.raise_for_status()
                latest = int(str(latest_response.json().get("result") or "0x0"), 16)
                block = int(str(receipt.get("blockNumber") or "0x0"), 16)
                confirmations = max(0, latest - block + 1)

            if confirmations < BSC_MIN_CONFIRMATIONS:
                return {
                    "state": "pending",
                    "reason": "waiting_confirmations",
                    "confirmations": confirmations,
                    "required_confirmations": BSC_MIN_CONFIRMATIONS,
                }

            return {
                "state": "confirmed",
                "reason": "confirmed",
                "amount": str(amount),
                "asset": "BNB",
                "network": "bsc",
                "provider": rpc_url,
                "confirmations": confirmations,
            }

        except Exception as exc:
            last_error = str(exc)[:400]

    return {"state": "pending", "reason": "bsc_rpc_unavailable", "error": last_error}


async def verify_native_crypto_intent(intent_id: int, db: Session) -> dict:
    if not _crypto_auto_verify_enabled(db):
        return {"ok": True, "verified": False, "reason": "crypto_auto_verify_disabled"}

    intent = db.get(PaymentIntent, int(intent_id))
    if intent is None:
        return {"ok": False, "verified": False, "reason": "payment_not_found"}

    method = str(intent.method or "").lower()
    if method not in {"trx_tron", "bnb_bsc"}:
        return {"ok": True, "verified": False, "reason": "not_native_crypto"}

    if intent.status in {"approved", "auto_verified", "paid"}:
        return {"ok": True, "verified": True, "reason": "already_verified"}

    txid = str(intent.txid or "").strip()
    if not txid:
        return {"ok": True, "verified": False, "reason": "txid_missing"}

    settings = native_gateway_settings(db)

    if method == "trx_tron":
        destination = str(settings.get("trx_tron_address") or "").strip()
        chain_result = await _verify_trx(txid, destination)
    else:
        destination = str(settings.get("bnb_bsc_address") or "").strip()
        chain_result = await _verify_bnb(txid, destination)

    if str(chain_result.get("state") or "pending") != "confirmed":
        intent.review_note = (
            "auto-native-chain-check: " + str(chain_result.get("reason") or "unknown")
        )[:1000]
        db.commit()
        return {"ok": True, "verified": False, **chain_result}

    try:
        received = Decimal(str(chain_result.get("amount") or "0"))
        expected = Decimal(str(intent.crypto_amount_usdt or "0"))
    except InvalidOperation:
        return {"ok": False, "verified": False, "reason": "invalid_expected_amount"}

    if expected <= 0:
        return {"ok": False, "verified": False, "reason": "expected_amount_missing"}

    if received < expected:
        intent.review_note = (
            f"auto-native-chain-check: amount_too_low expected={expected} received={received}"
        )[:1000]
        db.commit()
        return {
            "ok": True,
            "verified": False,
            "state": "invalid",
            "reason": "amount_too_low",
            "expected": str(expected),
            "received": str(received),
        }

    intent = (
        db.query(PaymentIntent)
        .filter(PaymentIntent.id == int(intent_id))
        .with_for_update()
        .first()
    )

    if intent is None:
        return {"ok": False, "verified": False, "reason": "payment_not_found"}
    if intent.status in {"approved", "auto_verified", "paid"}:
        return {"ok": True, "verified": True, "reason": "already_verified"}

    now = datetime.utcnow()
    intent.status = "auto_verified"
    intent.verified_at = now
    intent.review_note = (
        f"auto-native-verified: {method} amount={received}"
    )[:1000]

    order = db.get(StoreOrder, intent.order_id)
    if order is None:
        db.rollback()
        return {"ok": False, "verified": False, "reason": "order_missing"}

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
        order_result = await _fulfill_paid_order(order.id, db)
        fulfilled = True
    except HTTPException as exc:
        fulfillment_error = exc.detail

    if fulfilled:
        try:
            final_order = db.get(StoreOrder, order.id)
            subscription_id = final_order.subscription_id if final_order else None
            subscription = db.get(Subscription, subscription_id) if subscription_id else None

            queue_telegram_notification(
                db,
                user_id=intent.user_id,
                event_key=f"payment-auto-approved:{intent.id}",
                kind="payment_approved",
                payload={
                    "payment_id": intent.id,
                    "order_id": order.id,
                    "subscription_id": subscription_id,
                    "username": subscription.account_username if subscription else None,
                    "amount_toman": int(intent.base_amount_toman or 0),
                },
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            print("auto native crypto notification failed:", str(exc), flush=True)

    return {
        "ok": True,
        "verified": True,
        "fulfilled": fulfilled,
        "fulfillment_error": fulfillment_error,
        "order": order_result,
        **chain_result,
    }


async def process_pending_native_crypto_once(limit: int = 50) -> dict:
    lookup_db = SessionLocal()
    try:
        ids = [
            int(row[0])
            for row in (
                lookup_db.query(PaymentIntent.id)
                .filter(
                    PaymentIntent.method.in_(["trx_tron", "bnb_bsc"]),
                    PaymentIntent.txid.isnot(None),
                    PaymentIntent.status.in_(["awaiting_review", "payment_submitted"]),
                )
                .order_by(PaymentIntent.id.asc())
                .limit(max(1, min(int(limit), 200)))
                .all()
            )
        ]
    finally:
        lookup_db.close()

    checked = verified = errors = 0

    for intent_id in ids:
        db = SessionLocal()
        try:
            result = await verify_native_crypto_intent(intent_id, db)
            checked += 1
            if result.get("verified"):
                verified += 1
        except Exception as exc:
            errors += 1
            db.rollback()
            print("native crypto auto verification failed:", intent_id, str(exc), flush=True)
        finally:
            db.close()

    return {"ok": errors == 0, "checked": checked, "verified": verified, "errors": errors}
