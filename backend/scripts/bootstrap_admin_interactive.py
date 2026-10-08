#!/usr/bin/env python3
from __future__ import annotations

import getpass
import sys
from pathlib import Path

from pydantic import EmailStr, TypeAdapter, ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password


def ask_email() -> str:
    while True:
        value = input("Admin email: ").strip().lower()
        try:
            return str(TypeAdapter(EmailStr).validate_python(value)).lower()
        except ValidationError:
            print("Invalid email. Try again.")


def ask_password() -> str:
    while True:
        first = getpass.getpass("Admin password (typing is hidden): ")
        if len(first) < 10:
            print("Password must be at least 10 characters.")
            continue
        second = getpass.getpass("Confirm password: ")
        if first != second:
            print("Passwords do not match. Try again.")
            continue
        return first


def main() -> int:
    print("\nTwinPanel admin setup")
    print("Enter the admin email, then password. Password characters are hidden.\n")

    email = ask_email()
    password = ask_password()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(
                email=email,
                full_name="Administrator",
                password_hash=hash_password(password),
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(user)
            action = "created"
        else:
            user.password_hash = hash_password(password)
            user.role = UserRole.ADMIN
            user.is_active = True
            if not str(user.full_name or "").strip():
                user.full_name = "Administrator"
            action = "updated"

        db.commit()
        db.refresh(user)
        print(f"\nADMIN_READY action={action} email={user.email}")
        print("You can now sign in to TwinPanel with this email and password.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
