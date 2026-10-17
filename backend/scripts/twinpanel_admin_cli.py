#!/usr/bin/env python3
from __future__ import annotations

import argparse
import secrets
import string
import sys

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password


def _admin(db):
    row = (
        db.query(User)
        .filter(User.role == UserRole.ADMIN)
        .order_by(User.id.asc())
        .first()
    )
    if row is None:
        raise RuntimeError("ADMIN_NOT_FOUND")
    return row


def _password() -> str:
    alphabet = string.ascii_letters + string.digits + "-_.@"
    return "".join(secrets.choice(alphabet) for _ in range(20))


def _email(value: str) -> str:
    try:
        return str(TypeAdapter(EmailStr).validate_python(value)).lower()
    except ValidationError as exc:
        raise ValueError("INVALID_EMAIL") from exc


def cmd_show() -> int:
    db = SessionLocal()
    try:
        admin = _admin(db)
        print(f"ID={admin.id}")
        print(f"EMAIL={admin.email}")
        print(f"NAME={admin.full_name or ''}")
        print(f"ACTIVE={1 if admin.is_active else 0}")
        return 0
    finally:
        db.close()


def cmd_reset_password(value: str | None) -> int:
    password = (value or "").strip() or _password()
    if len(password) < 10:
        raise ValueError("PASSWORD_TOO_SHORT")

    db = SessionLocal()
    try:
        admin = _admin(db)
        admin.password_hash = hash_password(password)
        admin.is_active = True
        db.commit()
        print(f"ADMIN_EMAIL={admin.email}")
        print(f"ADMIN_PASSWORD={password}")
        print("PASSWORD_RESET_OK=1")
        return 0
    finally:
        db.close()


def cmd_change_email(value: str) -> int:
    email = _email(value.strip())
    db = SessionLocal()
    try:
        admin = _admin(db)
        duplicate = (
            db.query(User)
            .filter(User.email == email, User.id != admin.id)
            .first()
        )
        if duplicate is not None:
            raise RuntimeError("EMAIL_ALREADY_EXISTS")
        admin.email = email
        db.commit()
        print(f"ADMIN_EMAIL={admin.email}")
        print("EMAIL_UPDATED_OK=1")
        return 0
    finally:
        db.close()


def cmd_change_name(value: str) -> int:
    name = value.strip()
    if not name:
        raise ValueError("NAME_REQUIRED")
    db = SessionLocal()
    try:
        admin = _admin(db)
        admin.full_name = name
        db.commit()
        print(f"ADMIN_NAME={admin.full_name}")
        print("NAME_UPDATED_OK=1")
        return 0
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="TwinPanel administrator maintenance")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show")
    reset = sub.add_parser("reset-password")
    reset.add_argument("--password", default=None)
    email = sub.add_parser("change-email")
    email.add_argument("email")
    name = sub.add_parser("change-name")
    name.add_argument("name")
    args = parser.parse_args()

    try:
        if args.command == "show":
            return cmd_show()
        if args.command == "reset-password":
            return cmd_reset_password(args.password)
        if args.command == "change-email":
            return cmd_change_email(args.email)
        if args.command == "change-name":
            return cmd_change_name(args.name)
        return 2
    except Exception as exc:
        print(f"ERROR={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
