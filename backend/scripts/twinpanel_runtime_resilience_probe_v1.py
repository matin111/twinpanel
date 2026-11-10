#!/usr/bin/env python3
"""Safe recurring, read-only TwinPanel controller resilience check.

Never restarts an application or changes configuration, accounts or nodes.
Output is a small JSON event suitable for journald/monitoring.
"""
from __future__ import annotations
import argparse
import json
import subprocess
import time
import urllib.request
from pathlib import Path

CURRENT = Path("/opt/twinpanel/current")
SLOT_STATE = Path("/var/lib/twinpanel-license/web-slot-state.json")
REQUIRED = (
    "twinpanel-api.service",
    "twinpanel-modern-accounting.service",
    "twinpanel-bot.service",
    "twinpanel-reseller-bots.service",
    "nginx.service",
    "postgresql.service",
    "redis-server.service",
)


def run(*argv: str, timeout: int = 8) -> tuple[int, str]:
    try:
        cp = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, check=False, timeout=timeout)
        return cp.returncode, (cp.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""


def http_version(port: int) -> str | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
            if r.status != 200:
                return None
            doc = json.loads(r.read(4096))
        if doc.get("ok") is True:
            return str(doc.get("version") or "")
    except Exception:
        pass
    return None


def report() -> dict:
    errors: list[str] = []
    version = (CURRENT / "VERSION").read_text().strip() if (CURRENT / "VERSION").is_file() else ""
    if not version:
        errors.append("release_version_missing")
    try:
        state = json.loads(SLOT_STATE.read_text())
        port = int(state.get("active_port"))
        release = str(state.get("release") or "")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        port, release = 0, ""
        errors.append("web_route_state_missing")
    if port not in (3000, 3001):
        errors.append("web_route_invalid")
    if release != str(CURRENT.resolve()):
        errors.append("web_release_mismatch")

    services: dict[str, str] = {}
    for unit in REQUIRED:
        code, value = run("systemctl", "is-active", unit)
        services[unit.removesuffix(".service")] = value if code == 0 else "inactive"
        if code != 0:
            errors.append("inactive_service:" + unit)
    expected_web = "twinpanel-web.service" if port == 3000 else f"twinpanel-web-slot@{port}.service"
    code, value = run("systemctl", "is-active", expected_web)
    services["active_web_unit"] = value if code == 0 else "inactive"
    if code != 0:
        errors.append("active_web_unit_inactive")
    if version and http_version(8095) != version:
        errors.append("api_version_or_health_failure")
    if port and version and http_version(port) != version:
        errors.append("web_version_or_health_failure")
    if run("nginx", "-t", timeout=5)[0]:
        errors.append("nginx_configuration_invalid")
    db_sql = (
        "SELECT count(*),coalesce(max(round(extract(epoch from now()-xact_start))),0) "
        "FROM pg_stat_activity WHERE datname='twinpanel' "
        "AND state='idle in transaction' "
        "AND xact_start<now()-interval '60 seconds'"
    )
    code, db = run(
        "runuser", "-u", "postgres", "--", "psql", "-X", "-A", "-t", "-d", "postgres",
        "-c", db_sql, timeout=8,
    )
    stale = 0
    max_age = 0
    if code == 0 and "|" in db:
        try:
            stale, max_age = [int(float(x)) for x in db.split("|", 1)]
        except ValueError:
            errors.append("postgres_txn_audit_parse_error")
    else:
        errors.append("postgres_txn_audit_unavailable")
    if stale:
        errors.append("idle_postgres_transactions_over_60s")
    return {
        "event": "twinpanel_resilience_probe_v1",
        "healthy": not errors,
        "release": version,
        "active_web_port": port,
        "service_status": services,
        "stale_db_transactions": stale,
        "oldest_stale_seconds": max_age,
        "errors": errors,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()
    status = report()
    print(json.dumps(status, separators=(",", ":"), ensure_ascii=False), flush=True)
    return 2 if args.strict and not status["healthy"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
