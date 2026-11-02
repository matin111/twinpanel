from __future__ import annotations

from datetime import datetime, timezone


def _parse_iso(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _notify_if_expiring(state: dict) -> None:
    try:
        from .database import SessionLocal
        from .models import User, UserRole
        from .telegram_notify_service import queue_telegram_notification

        expiry = _parse_iso(state.get("expires_at") or state.get("trial_expires_at"))
        if expiry is None:
            return

        remaining = int((expiry - datetime.now(timezone.utc)).total_seconds())
        if remaining <= 0 or remaining > 3 * 86400:
            return

        days = max(1, (remaining + 86399) // 86400)
        stamp = expiry.strftime("%Y%m%d%H%M")
        db = SessionLocal()
        try:
            admins = (
                db.query(User)
                .filter(User.role == UserRole.ADMIN, User.is_active == True)
                .all()
            )
            for admin in admins:
                queue_telegram_notification(
                    db,
                    user_id=int(admin.id),
                    event_key=f"license-expiring:{stamp}:admin:{int(admin.id)}",
                    kind="user_notification",
                    payload={
                        "title": "هشدار پایان لایسنس TwinPanel",
                        "message": (
                            f"تنها {days} روز تا پایان لایسنس پنل باقی مانده است. "
                            "برای جلوگیری از محدود شدن عملیات مدیریتی، لایسنس را تمدید کنید."
                        ),
                    },
                )
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
    except Exception:
        pass


def install() -> None:
    from . import system_release

    original = system_release.validate_license
    if getattr(original, "_twinpanel_license_expiry_telegram_v1", False):
        return

    def validate_license_with_expiry_notice():
        state = original()
        _notify_if_expiring(dict(state or {}))
        return state

    validate_license_with_expiry_notice._twinpanel_license_expiry_telegram_v1 = True
    system_release.validate_license = validate_license_with_expiry_notice
