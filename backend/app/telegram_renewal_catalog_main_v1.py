"""Customer Telegram bot: choose any purchasable plan for renewing an existing account.

This reuses the same type > device count > category > plan taxonomy as the
purchase bot. The selected plan is sent to the renewal-order API and affects
only purchased traffic / validity; user credentials and account IDs stay put.
"""
from __future__ import annotations

from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .telegram_navigation_v1 import show_navigation_page
from .telegram_purchase_bot import (
    category_icon,
    plan_category,
    plan_subscription_type,
    plan_user_count,
    subscription_type_icon,
    user_count_icon,
)


def eligible_renewal_plans(rows):
    return [
        item for item in (rows if isinstance(rows, list) else [])
        if item.get("is_active", True) is True
        and not str(item.get("name") or "").startswith("__tp_reseller__")
        and int(item.get("price_toman") or 0) > 0
        and int(item.get("duration_days") or 0) > 0
        and int(item.get("traffic_gb") or 0) > 0
    ]


def renewal_plan_button_label(plan):
    """Small readable label; the category already carries the duration.

    The plan name commonly already includes quota (e.g. «30 گیگ»), so do
    not repeat the volume or show day counts in each inline keyboard button.
    """
    name = " ".join(str(plan.get("name") or "پلن").split())
    price = int(plan.get("price_toman") or 0)
    return f"{name}  |  {price:,} تومان"[:64]


def renewal_stage_markup(
    plans, subscription_id, step="type",
    type_index=None, user_count=None, category_index=None, page=0,
):
    """Return (title, keyboard) with no side effects; useful for regression tests."""
    sub_id = int(subscription_id)
    kinds = list(dict.fromkeys(plan_subscription_type(plan) for plan in plans))
    if not kinds:
        raise ValueError("پلن فعالی برای تمدید وجود ندارد")
    rows = []

    if step == "type":
        title = "🔄 <b>تمدید اشتراک</b>\n\nابتدا نوع اشتراک را انتخاب کنید:"
        for index, kind in enumerate(kinds[:30]):
            rows.append([InlineKeyboardButton(
                text=(f"{subscription_type_icon(kind, index)} {kind}")[:60],
                callback_data=f"subrntype:{sub_id}:{index}",
            )])
        back = f"sub:{sub_id}"
    else:
        if type_index is None or not 0 <= int(type_index) < len(kinds):
            raise ValueError("نوع اشتراک انتخاب‌شده معتبر نیست")
        kind = kinds[int(type_index)]
        typed = [item for item in plans if plan_subscription_type(item) == kind]
        counts = sorted({plan_user_count(plan) for plan in typed})
        if step == "users":
            title = f"🔄 <b>{escape(kind)}</b>\n\nتعداد دستگاه مجاز را انتخاب کنید:"
            for count in counts[:30]:
                label = "نامحدود" if count == 0 else str(count)
                rows.append([InlineKeyboardButton(
                    text=f"{user_count_icon(count)} {label} دستگاه",
                    callback_data=f"subrnusers:{sub_id}:{type_index}:{count}",
                )])
            back = f"subrenew:{sub_id}"
        else:
            if user_count not in counts:
                raise ValueError("تعداد دستگاه انتخاب‌شده معتبر نیست")
            selected = [p for p in typed if plan_user_count(p) == user_count]
            categories = list(dict.fromkeys(plan_category(p) for p in selected))
            if step == "category":
                title = "📂 <b>دسته‌بندی پلن تمدید</b>\n\nدسته‌بندی را انتخاب کنید:"
                for index, category in enumerate(categories[:30]):
                    rows.append([InlineKeyboardButton(
                        text=(f"{category_icon(category, index)} {category}")[:60],
                        callback_data=f"subrncat:{sub_id}:{type_index}:{user_count}:{index}",
                    )])
                back = f"subrntype:{sub_id}:{type_index}"
            elif step == "plans":
                if category_index is None or not 0 <= int(category_index) < len(categories):
                    raise ValueError("دسته‌بندی انتخاب‌شده معتبر نیست")
                category = categories[int(category_index)]
                matching = [p for p in selected if plan_category(p) == category]
                start = max(0, int(page)) * 12
                if start >= len(matching):
                    raise ValueError("صفحه پلن معتبر نیست")
                title = (
                    "🔄 <b>انتخاب پلن تمدید</b>\n"
                    f"📂 {escape(category)} | "
                    f"{'نامحدود' if user_count == 0 else user_count} دستگاه\n\n"
                    "حجم و اعتبار پلن انتخابی پس از پرداخت به همین اکانت اضافه می‌شود."
                )
                for item in matching[start:start + 12]:
                    rows.append([InlineKeyboardButton(
                        text=renewal_plan_button_label(item),
                        callback_data=f"subrnplan:{sub_id}:{int(item['id'])}",
                    )])
                nav = []
                if start > 0:
                    nav.append(InlineKeyboardButton(
                        text="⬅️ قبلی",
                        callback_data=f"subrnpage:{sub_id}:{type_index}:{user_count}:{category_index}:{page-1}",
                    ))
                if start + 12 < len(matching):
                    nav.append(InlineKeyboardButton(
                        text="بعدی ➡️",
                        callback_data=f"subrnpage:{sub_id}:{type_index}:{user_count}:{category_index}:{page+1}",
                    ))
                if nav:
                    rows.append(nav)
                back = f"subrnusers:{sub_id}:{type_index}:{user_count}"
            else:
                raise ValueError("مرحله تمدید ناشناخته است")

    rows.append([InlineKeyboardButton(
        text="⬅️ بازگشت", callback_data=back,
    )])
    return title, InlineKeyboardMarkup(inline_keyboard=rows)


async def load_renewal_catalog(
    telegram_user_id, subscription_id, *, request_fn, load_manage_fn,
):
    _token, info = await load_manage_fn(int(telegram_user_id), int(subscription_id))
    if not info.get("can_renew"):
        raise ValueError("وضعیت اشتراک اجازه تمدید نمی‌دهد")
    plans = eligible_renewal_plans(await request_fn("GET", "/v1/plans"))
    if not plans:
        raise ValueError("در حال حاضر پلن تمدید فعالی وجود ندارد")
    return plans


async def show_renewal_stage(
    callback, sub_id, *, request_fn, load_manage_fn,
    step="type", type_index=None, user_count=None, category_index=None, page=0,
):
    plans = await load_renewal_catalog(
        callback.from_user.id, sub_id, request_fn=request_fn,
        load_manage_fn=load_manage_fn,
    )
    title, markup = renewal_stage_markup(
        plans, sub_id, step, type_index, user_count, category_index, page,
    )
    await show_navigation_page(callback.message, title, reply_markup=markup)


async def load_selected_renewal_plan(
    telegram_user_id, subscription_id, plan_id, *, request_fn, load_manage_fn,
):
    plans = await load_renewal_catalog(
        telegram_user_id, subscription_id,
        request_fn=request_fn, load_manage_fn=load_manage_fn,
    )
    plan = next((p for p in plans if int(p["id"]) == int(plan_id)), None)
    if plan is None:
        raise ValueError("پلن انتخاب‌شده دیگر قابل خرید نیست")
    return plan
