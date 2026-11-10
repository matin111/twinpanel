#!/usr/bin/env python3
"""TwinPanel host reliability policy: idempotent, scope-limited and auditable.

No VPN dataplane, active subscription, credentials, Redis, Nginx or service
restart. PostgreSQL setting applies only to *new connections* to twinpanel.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

JOURNAL_DROPIN = Path("/etc/systemd/journald.conf.d/90-twinpanel-resilience.conf")
JOURNAL_TEXT = """# TwinPanel controller: disk-pressure guard without suppressing journal events.
# Retain recent evidence for debugging, but never consume unlimited disk.
[Journal]
SystemMaxUse=2G
SystemKeepFree=3G
MaxRetentionSec=14day
"""
DB_NAME = "twinpanel"
DB_IDLE_LIMIT = "180s"
VALID_DB = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def run(*args: str) -> str:
    cp = subprocess.run(
        list(args), text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=30, check=False,
    )
    if cp.returncode:
        raise RuntimeError(f"RESILIENCE_COMMAND_FAILED:{args[0]}:{cp.returncode}:{(cp.stdout or '')[-400:]}")
    return (cp.stdout or "").strip()


def db_config() -> str:
    # Uses postgres peer auth on the host; never reads or logs a password.
    # pg_db_role_setting is the authoritative catalog for ALTER DATABASE SET.
    sql = (
        "SELECT coalesce((SELECT array_to_string(setconfig,',') "
        "FROM pg_db_role_setting WHERE setdatabase = "
        "(SELECT oid FROM pg_database WHERE datname='twinpanel') "
        "AND setrole=0 LIMIT 1),'')"
    )
    return run("runuser", "-u", "postgres", "--", "psql",
               "-X", "-A", "-t", "-d", "postgres", "-c", sql)


def inspect() -> dict:
    installed = JOURNAL_DROPIN.read_text() if JOURNAL_DROPIN.is_file() else ""
    catalog = db_config()
    return {
        "journal_policy_installed": installed == JOURNAL_TEXT,
        "journal_policy_path": str(JOURNAL_DROPIN),
        "postgres_db_scope": DB_NAME,
        "postgres_idle_guard_enabled": (
            "idle_in_transaction_session_timeout=180s" in catalog
            or "idle_in_transaction_session_timeout=3min" in catalog
            or "idle_in_transaction_session_timeout=180000" in catalog
        ),
        "postgres_settings": [
            key.split("=", 1)[0] for key in catalog.split(",") if "=" in key
        ],
    }


def apply(*, journal_cleanup: bool = False) -> dict:
    if os.geteuid() != 0:
        raise RuntimeError("RESILIENCE_ROOT_REQUIRED")
    if not VALID_DB.fullmatch(DB_NAME):
        raise RuntimeError("RESILIENCE_INVALID_DB_NAME")
    # Fail closed if not a canonical TwinPanel installation.
    if not Path("/opt/twinpanel/current/VERSION").is_file():
        raise RuntimeError("RESILIENCE_TWINPANEL_INSTALL_NOT_FOUND")
    if not JOURNAL_DROPIN.is_file() or JOURNAL_DROPIN.read_text() != JOURNAL_TEXT:
        JOURNAL_DROPIN.parent.mkdir(parents=True, exist_ok=True)
        import tempfile
        fd, name = tempfile.mkstemp(prefix=".twinpanel-journald-", dir=JOURNAL_DROPIN.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(JOURNAL_TEXT)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(name, 0o644)
            os.replace(name, JOURNAL_DROPIN)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    # Re-read journald policy without terminating journald or losing events.
    run("systemctl", "kill", "--signal=SIGHUP", "systemd-journald.service")
    # PostgreSQL ALTER DATABASE changes new connections only and does NOT
    # disconnect or roll back current billing transactions.
    sql = f"ALTER DATABASE {DB_NAME} SET idle_in_transaction_session_timeout = '{DB_IDLE_LIMIT}'"
    run("runuser", "-u", "postgres", "--", "psql", "-X", "-v",
        "ON_ERROR_STOP=1", "-d", "postgres", "-c", sql)
    if journal_cleanup:
        # Explicit opt-in: a journal rotation can make older log records
        # eligible for vacuum. It never deletes application/user data.
        run("journalctl", "--rotate")
        run("journalctl", "--vacuum-size=2G")
    outcome = inspect()
    if not outcome["journal_policy_installed"] or not outcome["postgres_idle_guard_enabled"]:
        raise RuntimeError("RESILIENCE_POLICY_VERIFICATION_FAILED")
    return outcome


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--vacuum-journal", action="store_true")
    args = p.parse_args()
    if args.vacuum_journal and not args.apply:
        p.error("--vacuum-journal requires --apply")
    status = apply(journal_cleanup=args.vacuum_journal) if args.apply else inspect()
    print(json.dumps(status, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
