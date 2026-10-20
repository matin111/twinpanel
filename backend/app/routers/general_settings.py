# TWINPANEL_USERNAME_SETTINGS_API_V2

from datetime import datetime
import re

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..database import (
    SessionLocal,
    get_db,
)
from ..deps import require_admin


router = APIRouter(
    prefix="/v1/settings/general",
    tags=["settings"],
)


PREFIX_KEY = (
    "subscription_username_prefix"
)

TEMPLATE_KEY = (
    "subscription_username_template"
)

DEFAULT_PREFIX = "mv"

DEFAULT_TEMPLATE = (
    "{prefix}{sub_id}_{user_id}"
)

ALLOWED_FIELDS = {
    "prefix",
    "sub_id",
    "user_id",
}


class SubscriptionUsernameSettingsIn(
    BaseModel
):
    prefix: str = Field(
        min_length=1,
        max_length=20,
    )

    template: str = Field(
        min_length=1,
        max_length=80,
    )


def _runtime_get(
    db: Session,
    key: str,
    default: str,
) -> str:

    value = db.execute(
        text(
            """
            SELECT setting_value
            FROM vpnshop_runtime_settings
            WHERE setting_key = :key
            LIMIT 1
            """
        ),
        {
            "key": key,
        },
    ).scalar_one_or_none()

    if value is None:
        return default

    value = str(value).strip()

    return value or default


def _runtime_set(
    db: Session,
    key: str,
    value: str,
) -> None:

    result = db.execute(
        text(
            """
            UPDATE vpnshop_runtime_settings
            SET
                setting_value = :value,
                updated_at = :updated_at
            WHERE setting_key = :key
            """
        ),
        {
            "key": key,
            "value": value,
            "updated_at": datetime.utcnow(),
        },
    )

    if int(result.rowcount or 0) == 0:

        db.execute(
            text(
                """
                INSERT INTO vpnshop_runtime_settings
                (
                    setting_key,
                    setting_value,
                    updated_at
                )
                VALUES
                (
                    :key,
                    :value,
                    :updated_at
                )
                """
            ),
            {
                "key": key,
                "value": value,
                "updated_at": datetime.utcnow(),
            },
        )


def _validate_prefix(
    value: str,
) -> str:

    value = str(
        value or ""
    ).strip()

    if not re.fullmatch(
        r"[A-Za-z0-9_-]{1,20}",
        value,
    ):
        raise ValueError(
            "پیشوند فقط می‌تواند شامل "
            "حروف انگلیسی، عدد، - و _ باشد"
        )

    return value


def _validate_template(
    value: str,
) -> str:

    value = str(
        value or ""
    ).strip()

    if (
        not value
        or len(value) > 80
    ):
        raise ValueError(
            "الگوی نام کاربری نامعتبر است"
        )

    fields = set(
        re.findall(
            r"\{([^{}]+)\}",
            value,
        )
    )

    unknown = (
        fields
        - ALLOWED_FIELDS
    )

    if unknown:
        raise ValueError(
            "متغیر نامعتبر در الگو: "
            + ", ".join(
                sorted(unknown)
            )
        )

    # Every subscription must remain unique.
    if "sub_id" not in fields:
        raise ValueError(
            "الگو باید شامل {sub_id} باشد"
        )

    test = value

    for field in ALLOWED_FIELDS:
        test = test.replace(
            "{" + field + "}",
            "1",
        )

    if (
        "{" in test
        or "}" in test
    ):
        raise ValueError(
            "ساختار متغیرهای الگو نامعتبر است"
        )

    try:
        preview = value.format(
            prefix="mv",
            sub_id=123,
            user_id=45,
        )
    except Exception as exc:
        raise ValueError(
            "الگوی نام کاربری قابل پردازش نیست"
        ) from exc

    safe = re.sub(
        r"[^A-Za-z0-9_-]",
        "",
        preview,
    )[:30]

    if not safe:
        raise ValueError(
            "خروجی الگو نمی‌تواند خالی باشد"
        )

    return value


def build_subscription_username(
    db: Session,
    sub_id: int,
    user_id: int,
) -> str:

    try:
        prefix = _validate_prefix(
            _runtime_get(
                db,
                PREFIX_KEY,
                DEFAULT_PREFIX,
            )
        )
    except Exception:
        prefix = DEFAULT_PREFIX

    try:
        template = _validate_template(
            _runtime_get(
                db,
                TEMPLATE_KEY,
                DEFAULT_TEMPLATE,
            )
        )
    except Exception:
        template = DEFAULT_TEMPLATE

    try:
        raw = template.format(
            prefix=prefix,
            sub_id=int(sub_id),
            user_id=int(user_id),
        )
    except Exception:
        raw = (
            f"mv{int(sub_id)}_"
            f"{int(user_id)}"
        )

    username = re.sub(
        r"[^A-Za-z0-9_-]",
        "",
        raw,
    )[:30]

    if not username:
        username = (
            f"mv{int(sub_id)}_"
            f"{int(user_id)}"
        )[:30]

    return username


def build_subscription_username_runtime(
    sub_id: int,
    user_id: int,
) -> str:
    """
    Read only username generation.

    Opens a short independent DB session so existing
    _safe_username(sub, user) call sites do not need
    to be changed.
    """

    db = SessionLocal()

    try:
        return build_subscription_username(
            db,
            sub_id,
            user_id,
        )
    finally:
        db.close()


def _settings_out(
    db: Session,
) -> dict:

    try:
        prefix = _validate_prefix(
            _runtime_get(
                db,
                PREFIX_KEY,
                DEFAULT_PREFIX,
            )
        )
    except Exception:
        prefix = DEFAULT_PREFIX

    try:
        template = _validate_template(
            _runtime_get(
                db,
                TEMPLATE_KEY,
                DEFAULT_TEMPLATE,
            )
        )
    except Exception:
        template = DEFAULT_TEMPLATE

    preview = build_subscription_username(
        db,
        123,
        45,
    )

    return {
        "prefix": prefix,
        "template": template,
        "preview": preview,
        "variables": [
            "{prefix}",
            "{sub_id}",
            "{user_id}",
        ],
    }


@router.get(
    "/subscription-username",
    dependencies=[
        Depends(require_admin)
    ],
)
def subscription_username_settings(
    db: Session = Depends(get_db),
):
    return _settings_out(db)


@router.put(
    "/subscription-username",
    dependencies=[
        Depends(require_admin)
    ],
)
def update_subscription_username_settings(
    payload:
        SubscriptionUsernameSettingsIn,
    db: Session = Depends(get_db),
):

    try:
        prefix = _validate_prefix(
            payload.prefix
        )

        template = _validate_template(
            payload.template
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    _runtime_set(
        db,
        PREFIX_KEY,
        prefix,
    )

    _runtime_set(
        db,
        TEMPLATE_KEY,
        template,
    )

    db.commit()

    return _settings_out(db)
