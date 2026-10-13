from __future__ import annotations

from datetime import datetime
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)


class WalletTopupState(StatesGroup):
    custom_amount = State()
    payment_method = State()
    tracking_code = State()
    card_last4 = State()
    transfer_date = State()
    transfer_time = State()
    txid = State()


def money(value):
    try:
        return f"{int(value or 0):,}"
    except Exception:
        return "0"


def fa_status(value):
    return {
        "pending_payment": "در انتظار پرداخت",
        "awaiting_review": "در حال تأیید خودکار",
        "approved": "تأیید و شارژ شده",
        "rejected": "رد شده",
    }.get(str(value or "").lower(), str(value or "-"))


def wallet_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ افزایش موجودی", callback_data="wallet:topup")],
        [
            InlineKeyboardButton(text="🧾 درخواست‌های شارژ", callback_data="wallet:topups"),
            InlineKeyboardButton(text="📋 گردش حساب", callback_data="wallet:transactions"),
        ],
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="wallet:refresh")],
    ])


def amount_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="100 هزار تومان", callback_data="wallet:amount:100000"),
            InlineKeyboardButton(text="200 هزار تومان", callback_data="wallet:amount:200000"),
        ],
        [
            InlineKeyboardButton(text="500 هزار تومان", callback_data="wallet:amount:500000"),
            InlineKeyboardButton(text="1 میلیون تومان", callback_data="wallet:amount:1000000"),
        ],
        [InlineKeyboardButton(text="✏️ مبلغ دلخواه", callback_data="wallet:amount:custom")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="wallet:refresh")],
    ])


def methods_keyboard(methods):
    rows = []
    for item in methods:
        method_id = str(item.get("id") or "")
        if not method_id:
            continue
        rows.append([
            InlineKeyboardButton(
                text=str(item.get("title") or method_id),
                callback_data=f"wallet:method:{method_id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ تغییر مبلغ", callback_data="wallet:topup")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def submit_keyboard(topup_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ ثبت اطلاعات پرداخت", callback_data=f"wallet:submit:{topup_id}")],
        [InlineKeyboardButton(text="💰 کیف پول", callback_data="wallet:refresh")],
    ])


async def _token(session_fn, telegram_id):
    data = await session_fn(telegram_id)
    return data["access_token"]


async def _wallet_data(request_fn, session_fn, telegram_id):
    token = await _token(session_fn, telegram_id)
    wallet = await request_fn("GET", "/v1/wallet/me", token=token)
    transactions = await request_fn("GET", "/v1/wallet/transactions", token=token)
    topups = await request_fn("GET", "/v1/wallet/topups/me", token=token)
    return (
        token,
        wallet or {},
        transactions if isinstance(transactions, list) else [],
        topups if isinstance(topups, list) else [],
    )


def wallet_text(wallet, transactions, topups):
    balance = int(wallet.get("balance_toman") or 0)
    pending = sum(1 for row in topups if row.get("status") in {"pending_payment", "awaiting_review"})
    approved = sum(1 for row in topups if row.get("status") == "approved")
    lines = [
        "💰 <b>کیف پول</b>",
        "",
        "موجودی قابل استفاده:",
        f"<b>{money(balance)} تومان</b>",
        "",
        f"🟡 درخواست باز: <b>{pending}</b>",
        f"✅ شارژ تأییدشده: <b>{approved}</b>",
    ]
    if transactions:
        row = transactions[0]
        amount = int(row.get("amount_toman") or 0)
        lines.extend([
            "",
            "📋 <b>آخرین تغییر موجودی</b>",
            f"{'+' if amount > 0 else ''}{money(amount)} تومان",
        ])
        if row.get("description"):
            lines.append(escape(str(row["description"])))
    return "\n".join(lines)


def _digits(value: str) -> str:
    return (
        str(value or "")
        .translate(str.maketrans(
            "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
            "01234567890123456789",
        ))
        .replace(",", "")
        .replace("٬", "")
        .replace(" ", "")
    )


def _asset(result: dict, payment: dict, method: str) -> str:
    value = str(result.get("crypto_asset") or payment.get("asset") or "").upper()
    if value:
        return value
    return {"usdt_bep20": "USDT", "trx_tron": "TRX", "bnb_bsc": "BNB"}.get(method, "CRYPTO")


def _crypto_amount(result: dict) -> str:
    return str(result.get("crypto_amount") or result.get("crypto_amount_usdt") or "-")


def create_wallet_router(request_fn, session_fn):
    router = Router(name="twinpanel-wallet-v2")

    async def send_wallet(target, telegram_id, *, edit=False):
        token, wallet, transactions, topups = await _wallet_data(request_fn, session_fn, telegram_id)
        text = wallet_text(wallet, transactions, topups)
        if edit:
            await target.edit_text(text, reply_markup=wallet_keyboard())
        else:
            await target.answer(text, reply_markup=wallet_keyboard())
        return token

    async def send_methods(target, telegram_id, state: FSMContext, amount: int, *, edit=False):
        token = await _token(session_fn, telegram_id)
        result = await request_fn("GET", "/v1/wallet/methods", token=token)
        methods = result.get("methods") or []
        if not methods:
            raise RuntimeError("روش پرداخت فعالی وجود ندارد")
        await state.update_data(amount_toman=amount)
        text = "💰 مبلغ شارژ:\n" f"<b>{money(amount)} تومان</b>\n\n" "روش پرداخت را انتخاب کنید:"
        if edit:
            await target.edit_text(text, reply_markup=methods_keyboard(methods))
        else:
            await target.answer(text, reply_markup=methods_keyboard(methods))

    @router.message(F.text == "💰 کیف پول")
    async def wallet_main(message: Message, state: FSMContext):
        await state.clear()
        try:
            await send_wallet(message, message.from_user.id)
        except Exception as exc:
            await message.answer("❌ " + escape(str(exc)))

    @router.callback_query(F.data == "wallet:refresh")
    async def wallet_refresh(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        try:
            await send_wallet(callback.message, callback.from_user.id, edit=True)
            await callback.answer()
        except Exception as exc:
            await callback.answer(str(exc), show_alert=True)

    @router.callback_query(F.data == "wallet:topup")
    async def wallet_topup(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.answer()
        await callback.message.edit_text(
            "➕ <b>افزایش موجودی کیف پول</b>\n\nمبلغ موردنظر را انتخاب کنید:",
            reply_markup=amount_keyboard(),
        )

    @router.callback_query(F.data.startswith("wallet:amount:"))
    async def wallet_amount(callback: CallbackQuery, state: FSMContext):
        value = callback.data.split(":", 2)[2]
        if value == "custom":
            await state.set_state(WalletTopupState.custom_amount)
            await callback.answer()
            await callback.message.edit_text("✏️ مبلغ موردنظر را به تومان ارسال کنید.\n\nحداقل: 10,000 تومان")
            return
        try:
            await send_methods(callback.message, callback.from_user.id, state, int(value), edit=True)
            await callback.answer()
        except Exception as exc:
            await callback.answer(str(exc), show_alert=True)

    @router.message(WalletTopupState.custom_amount)
    async def wallet_custom_amount(message: Message, state: FSMContext):
        raw = _digits(message.text or "")
        if not raw.isdigit() or int(raw) < 10_000:
            await message.answer("❌ مبلغ معتبر نیست. حداقل مبلغ 10,000 تومان است.")
            return
        amount = int(raw)
        if amount > 100_000_000:
            await message.answer("❌ مبلغ بیشتر از حد مجاز است.")
            return
        try:
            await send_methods(message, message.from_user.id, state, amount)
        except Exception as exc:
            await message.answer("❌ " + escape(str(exc)))

    @router.callback_query(F.data.startswith("wallet:method:"))
    async def wallet_method(callback: CallbackQuery, state: FSMContext):
        method = callback.data.split(":", 2)[2]
        data = await state.get_data()
        amount = int(data.get("amount_toman") or 0)
        if amount < 10_000:
            await callback.answer("ابتدا مبلغ را انتخاب کنید", show_alert=True)
            return
        try:
            token = await _token(session_fn, callback.from_user.id)
            result = await request_fn(
                "POST", "/v1/wallet/topups", token=token,
                payload={"amount_toman": amount, "method": method},
            )
        except Exception as exc:
            await callback.answer(str(exc), show_alert=True)
            return

        payment = result.get("payment_method") or {}
        asset = _asset(result, payment, method)
        await state.update_data(topup_id=int(result["id"]), payment_method=method, crypto_asset=asset)
        await callback.answer()

        if method == "card_to_card":
            payable = int(result.get("payable_amount_toman") or amount)
            text = (
                "💳 <b>شارژ کیف پول - کارت به کارت</b>\n\n"
                f"موجودی افزوده‌شونده: <b>{money(amount)} تومان</b>\n"
                f"مبلغ دقیق قابل پرداخت: <b>{money(payable)} تومان</b>\n\n"
                "شماره کارت:\n"
                f"<code>{escape(str(payment.get('card_number') or '-'))}</code>\n"
                f"به نام: <b>{escape(str(payment.get('card_holder') or '-'))}</b>\n\n"
                "⚠️ مبلغ را دقیقاً مطابق عدد بالا پرداخت کنید تا SMS Reader آن را خودکار تأیید کند."
            )
        else:
            exact = _crypto_amount(result)
            rate = int(result.get("crypto_rate_toman") or 0)
            text = (
                f"🪙 <b>شارژ کیف پول با {escape(asset)}</b>\n\n"
                f"موجودی افزوده‌شونده: <b>{money(amount)} تومان</b>\n"
                f"مقدار دقیق: <b>{escape(exact)} {escape(asset)}</b>\n"
                + (f"نرخ فریز‌شده: <b>{money(rate)} / {escape(asset)}</b>\n" if rate else "")
                + "\nآدرس کیف پول:\n"
                f"<code>{escape(str(payment.get('address') or '-'))}</code>\n\n"
                "پس از ثبت TXID، شبکه خودکار بررسی و کیف پول خودکار شارژ می‌شود."
            )

        await callback.message.edit_text(text, reply_markup=submit_keyboard(int(result["id"])))

    @router.callback_query(F.data.startswith("wallet:submit:"))
    async def wallet_submit_start(callback: CallbackQuery, state: FSMContext):
        topup_id = int(callback.data.split(":")[2])
        data = await state.get_data()
        method = str(data.get("payment_method") or "")
        await state.update_data(topup_id=topup_id)
        await callback.answer()
        if method == "card_to_card":
            await state.set_state(WalletTopupState.tracking_code)
            await callback.message.answer("🧾 کد پیگیری کارت‌به‌کارت را ارسال کنید.")
        else:
            await state.set_state(WalletTopupState.txid)
            asset = str(data.get("crypto_asset") or "ارز دیجیتال")
            await callback.message.answer(f"🔗 TXID تراکنش {escape(asset)} را ارسال کنید.")

    @router.message(WalletTopupState.tracking_code)
    async def wallet_tracking(message: Message, state: FSMContext):
        value = (message.text or "").strip()
        if len(value) < 3:
            await message.answer("❌ کد پیگیری معتبر نیست.")
            return
        await state.update_data(tracking_code=value)
        await state.set_state(WalletTopupState.card_last4)
        await message.answer("💳 ۴ رقم آخر کارت مبدا را ارسال کنید.\nمثال: <code>1234</code>")

    @router.message(WalletTopupState.card_last4)
    async def wallet_card_last4(message: Message, state: FSMContext):
        raw = _digits(message.text or "")
        if len(raw) != 4 or not raw.isdigit():
            await message.answer("❌ فقط ۴ رقم آخر کارت را ارسال کنید.")
            return
        await state.update_data(sender_card_last4=raw)
        await state.set_state(WalletTopupState.transfer_date)
        await message.answer("📅 تاریخ پرداخت را ارسال کنید.\nمثال: <code>2026-08-31</code>")

    @router.message(WalletTopupState.transfer_date)
    async def wallet_date(message: Message, state: FSMContext):
        value = _digits(message.text or "").replace("/", "-")
        try:
            value = datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d")
        except Exception:
            await message.answer("❌ تاریخ معتبر نیست. مثال: <code>2026-08-31</code>")
            return
        await state.update_data(transfer_date=value)
        await state.set_state(WalletTopupState.transfer_time)
        await message.answer("🕐 ساعت پرداخت را ارسال کنید.\nمثال: <code>14:25</code>")

    @router.message(WalletTopupState.transfer_time)
    async def wallet_time(message: Message, state: FSMContext):
        value = _digits(message.text or "")
        try:
            value = datetime.strptime(value, "%H:%M").strftime("%H:%M")
        except Exception:
            await message.answer("❌ ساعت معتبر نیست. مثال: <code>14:25</code>")
            return
        data = await state.get_data()
        try:
            token = await _token(session_fn, message.from_user.id)
            result = await request_fn(
                "POST", f"/v1/wallet/topups/{int(data['topup_id'])}/submit", token=token,
                payload={
                    "tracking_code": data["tracking_code"],
                    "sender_card_last4": data["sender_card_last4"],
                    "transfer_date": data["transfer_date"],
                    "transfer_time": value,
                },
            )
        except Exception as exc:
            await message.answer("❌ " + escape(str(exc)))
            return
        await state.clear()
        status = str(result.get("status") or "")
        await message.answer(
            "✅ <b>اطلاعات شارژ ثبت شد</b>\n\n"
            f"💰 مبلغ کیف پول: <b>{money(result.get('amount_toman'))} تومان</b>\n"
            + ("✅ موجودی شارژ شد." if status == "approved" else "🤖 SMS Reader پرداخت را خودکار بررسی می‌کند."),
            reply_markup=wallet_keyboard(),
        )

    @router.message(WalletTopupState.txid)
    async def wallet_txid(message: Message, state: FSMContext):
        txid = (message.text or "").strip()
        if len(txid) < 10:
            await message.answer("❌ TXID معتبر نیست.")
            return
        data = await state.get_data()
        try:
            token = await _token(session_fn, message.from_user.id)
            result = await request_fn(
                "POST", f"/v1/wallet/topups/{int(data['topup_id'])}/submit", token=token,
                payload={"txid": txid},
            )
        except Exception as exc:
            await message.answer("❌ " + escape(str(exc)))
            return
        await state.clear()
        status = str(result.get("status") or "")
        await message.answer(
            "✅ <b>TXID ثبت شد</b>\n\n"
            f"💰 مبلغ کیف پول: <b>{money(result.get('amount_toman'))} تومان</b>\n"
            + ("✅ تراکنش تأیید شد و موجودی شارژ شد." if status == "approved" else "🤖 شبکه به‌صورت خودکار بررسی می‌شود؛ پس از تأیید، موجودی خودکار اضافه خواهد شد."),
            reply_markup=wallet_keyboard(),
        )

    @router.callback_query(F.data == "wallet:topups")
    async def wallet_topups(callback: CallbackQuery):
        try:
            token = await _token(session_fn, callback.from_user.id)
            rows = await request_fn("GET", "/v1/wallet/topups/me", token=token)
        except Exception as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        rows = rows if isinstance(rows, list) else []
        lines = ["🧾 <b>درخواست‌های شارژ</b>"]
        if not rows:
            lines += ["", "درخواستی ثبت نشده است."]
        else:
            for row in rows[:10]:
                asset = str(row.get("crypto_asset") or "")
                exact = str(row.get("crypto_amount") or row.get("crypto_amount_usdt") or "")
                lines.extend(["", f"#{row.get('id')} • {money(row.get('amount_toman'))} تومان", f"وضعیت: <b>{escape(fa_status(row.get('status')))}</b>"])
                if asset and exact:
                    lines.append(f"پرداخت: <code>{escape(exact)} {escape(asset)}</code>")
        await callback.answer()
        await callback.message.edit_text("\n".join(lines), reply_markup=wallet_keyboard())

    @router.callback_query(F.data == "wallet:transactions")
    async def wallet_transactions(callback: CallbackQuery):
        try:
            token = await _token(session_fn, callback.from_user.id)
            rows = await request_fn("GET", "/v1/wallet/transactions", token=token)
        except Exception as exc:
            await callback.answer(str(exc), show_alert=True)
            return
        rows = rows if isinstance(rows, list) else []
        lines = ["📋 <b>گردش حساب کیف پول</b>"]
        if not rows:
            lines += ["", "هنوز تراکنشی ثبت نشده است."]
        else:
            for row in rows[:15]:
                amount = int(row.get("amount_toman") or 0)
                lines.extend(["", f"{'+' if amount > 0 else ''}{money(amount)} تومان", escape(str(row.get("description") or row.get("kind") or "-"))])
        await callback.answer()
        await callback.message.edit_text("\n".join(lines), reply_markup=wallet_keyboard())

    return router
