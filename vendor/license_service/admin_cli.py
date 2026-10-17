#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from app import (
    Activation,
    Base,
    KEY_PEPPER,
    License,
    RELEASE_ROOT,
    SessionLocal,
    Trial,
    engine,
    event,
    hash_license_key,
    iso,
    utcnow,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def new_key() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    groups = ["".join(secrets.choice(alphabet) for _ in range(6)) for _ in range(4)]
    return "TP-" + "-".join(groups)


def issue(args: argparse.Namespace) -> None:
    raw_key = new_key()
    expires = None if args.days <= 0 else utcnow() + timedelta(days=args.days)
    with SessionLocal() as db:
        row = License(
            key_hash=hash_license_key(raw_key),
            key_hint=raw_key[-8:],
            customer_ref=args.customer,
            edition=args.edition,
            status="active",
            starts_at=utcnow(),
            expires_at=expires,
            max_installations=args.max_installations,
            release_channel=args.channel,
        )
        db.add(row)
        db.flush()
        event(
            db,
            "license_issued",
            license_id=row.id,
            customer_ref=args.customer,
            edition=args.edition,
            expires_at=iso(expires),
            max_installations=args.max_installations,
        )
        db.commit()
        print("LICENSE_CREATED")
        print(f"ID={row.id}")
        print(f"KEY={raw_key}")
        print(f"CUSTOMER={args.customer}")
        print(f"EDITION={args.edition}")
        print(f"EXPIRES_AT={iso(expires) or 'NEVER'}")
        print("IMPORTANT=The plaintext key is shown only now. Store it securely.")


def license_action(args: argparse.Namespace) -> None:
    key_hash = hash_license_key(args.key)
    with SessionLocal() as db:
        row = db.scalar(select(License).where(License.key_hash == key_hash))
        if row is None:
            raise SystemExit("LICENSE_NOT_FOUND")
        # Keep activation rows bound while suspended/revoked so an installation
        # cannot fall back to an older Trial. state_for() will authoritatively
        # return suspended/revoked until the vendor changes the license state.
        row.status = args.action
        event(db, f"license_{args.action}", license_id=row.id)
        db.commit()
        print(f"LICENSE_{args.action.upper()}=OK")
        print(f"ID={row.id}")


def list_licenses(_: argparse.Namespace) -> None:
    with SessionLocal() as db:
        rows = db.scalars(select(License).order_by(License.id.desc())).all()
        for row in rows:
            active_count = len(
                db.scalars(
                    select(Activation).where(
                        Activation.license_id == row.id,
                        Activation.active.is_(True),
                    )
                ).all()
            )
            print(
                f"id={row.id} status={row.status} edition={row.edition} "
                f"customer={row.customer_ref!r} hint={row.key_hint} "
                f"active={active_count}/{row.max_installations} "
                f"expires={iso(row.expires_at) or 'never'} channel={row.release_channel}"
            )


def publish_release(args: argparse.Namespace) -> None:
    source = Path(args.file).resolve()
    if not source.is_file():
        raise SystemExit("RELEASE_FILE_NOT_FOUND")
    RELEASE_ROOT.mkdir(parents=True, exist_ok=True)
    filename = f"twinpanel-{args.version}.tar.gz"
    target = RELEASE_ROOT / filename
    if source != target.resolve():
        shutil.copy2(source, target)
    digest = sha256(target)
    metadata = {
        "product": "TwinPanel",
        "channel": args.channel,
        "version": args.version,
        "installable": bool(args.installable),
        "released_at": iso(utcnow()),
        "file": filename,
        "sha256": digest,
        "notes": {
            "fa": args.notes_fa,
            "en": args.notes_en,
        },
    }
    tmp = RELEASE_ROOT / f".{args.channel}.json.tmp"
    tmp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(RELEASE_ROOT / f"{args.channel}.json")
    print("RELEASE_PUBLISHED")
    print(f"VERSION={args.version}")
    print(f"CHANNEL={args.channel}")
    print(f"INSTALLABLE={str(bool(args.installable)).lower()}")
    print(f"FILE={target}")
    print(f"SHA256={digest}")


def trial_info(args: argparse.Namespace) -> None:
    fingerprint = args.fingerprint.strip().lower()
    with SessionLocal() as db:
        row = db.scalar(select(Trial).where(Trial.fingerprint_hash == fingerprint))
        if row is None:
            raise SystemExit("TRIAL_NOT_FOUND")
        print(f"ID={row.id}")
        print(f"STATUS={row.status}")
        print(f"STARTED_AT={iso(row.started_at)}")
        print(f"EXPIRES_AT={iso(row.expires_at)}")
        print(f"RESET_COUNT={row.reset_count}")


def reset_trial(args: argparse.Namespace) -> None:
    fingerprint = args.fingerprint.strip().lower()
    with SessionLocal() as db:
        row = db.scalar(select(Trial).where(Trial.fingerprint_hash == fingerprint))
        if row is None:
            started = utcnow()
            row = Trial(
                fingerprint_hash=fingerprint,
                started_at=started,
                expires_at=started + timedelta(days=7),
                status="active",
                reset_count=1,
            )
            db.add(row)
        else:
            row.started_at = utcnow()
            row.expires_at = row.started_at + timedelta(days=7)
            row.status = "active"
            row.reset_count = int(row.reset_count or 0) + 1
        event(db, "trial_reset", detail_reason=args.reason, fingerprint=fingerprint[:12])
        db.commit()
        print("TRIAL_RESET=OK")
        print(f"EXPIRES_AT={iso(row.expires_at)}")
        print(f"RESET_COUNT={row.reset_count}")


def init_db(_: argparse.Namespace) -> None:
    Base.metadata.create_all(engine)
    print("DATABASE_SCHEMA=OK")
    print(f"KEY_PEPPER_CONFIGURED={bool(KEY_PEPPER)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="TwinPanel vendor license administration")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init-db")
    p.set_defaults(func=init_db)

    p = sub.add_parser("issue")
    p.add_argument("--customer", required=True)
    p.add_argument("--days", type=int, default=30, help="0 = no expiry")
    p.add_argument("--edition", default="standard")
    p.add_argument("--channel", default="stable")
    p.add_argument("--max-installations", type=int, default=1)
    p.set_defaults(func=issue)

    for action in ("suspended", "revoked", "active"):
        p = sub.add_parser(action)
        p.add_argument("key")
        p.set_defaults(func=license_action, action=action)

    p = sub.add_parser("list")
    p.set_defaults(func=list_licenses)

    p = sub.add_parser("publish-release")
    p.add_argument("--version", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--channel", default="stable")
    p.add_argument("--installable", action="store_true")
    p.add_argument("--notes-fa", default="")
    p.add_argument("--notes-en", default="")
    p.set_defaults(func=publish_release)

    p = sub.add_parser("trial-info")
    p.add_argument("fingerprint")
    p.set_defaults(func=trial_info)

    p = sub.add_parser("reset-trial")
    p.add_argument("fingerprint")
    p.add_argument("--reason", required=True)
    p.set_defaults(func=reset_trial)

    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
