#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password


def need(name: str) -> str:
    value = str(os.getenv(name, "") or "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    email = need("TWINPANEL_ADMIN_EMAIL").lower()
    password = need("TWINPANEL_ADMIN_PASSWORD")
    full_name = str(os.getenv("TWINPANEL_ADMIN_NAME", "System Admin") or "System Admin").strip()

    if len(password) < 10:
        raise SystemExit("TWINPANEL_ADMIN_PASSWORD must be at least 10 characters")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()

        if user is None:
            user = User(
                email=email,
                full_name=full_name,
                password_hash=hash_password(password),
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(user)
            action = "created"
        else:
            user.full_name = full_name or user.full_name
            user.password_hash = hash_password(password)
            user.role = UserRole.ADMIN
            user.is_active = True
            action = "updated"

        db.commit()
        db.refresh(user)
        print(f"ADMIN_BOOTSTRAP_OK action={action} id={user.id} email={user.email}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
