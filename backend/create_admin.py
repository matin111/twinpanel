from __future__ import annotations

import getpass
import os
import sys

from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password


def _env(name: str) -> str:
    return str(os.getenv(name, "") or "").strip()


def _read_email() -> str:
    value = _env("TWINPANEL_ADMIN_EMAIL") or input("Admin email: ").strip()
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        raise SystemExit("Admin email is invalid")
    return value.lower()


def _read_name() -> str:
    return _env("TWINPANEL_ADMIN_NAME") or input("Admin full name: ").strip() or "TwinPanel Admin"


def _read_password() -> str:
    value = _env("TWINPANEL_ADMIN_PASSWORD")
    if not value:
        value = getpass.getpass("Admin password: ")
        confirm = getpass.getpass("Confirm password: ")
        if value != confirm:
            raise SystemExit("Passwords do not match")
    if len(value) < 12:
        raise SystemExit("Admin password must contain at least 12 characters")
    return value


def main() -> int:
    email = _read_email()
    full_name = _read_name()
    password = _read_password()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(user)
            action = "created"
        else:
            user.password_hash = hash_password(password)
            user.full_name = full_name or user.full_name
            user.role = UserRole.ADMIN
            user.is_active = True
            action = "updated"

        db.commit()
        db.refresh(user)
        print(f"ADMIN_READY action={action} id={user.id} email={user.email}")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Cancelled", file=sys.stderr)
        raise SystemExit(130)
