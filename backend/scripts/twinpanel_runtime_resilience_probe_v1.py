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
    # After a successful blue/green update *both* ports can be owned by a
    # pinned slot unit; on first migration port 3000 is still the legacy unit.
    # Never confuse an intentionally disabled legacy Web with an outage.
    candidate_units = [f"twinpanel-web-slot@{port}.service"]
    if port == 3000:
        candidate_units.append("twinpanel-web.service")
    web_alive = False
    for web_unit in candidate_units:
        result, _ = run("systemctl", "is-active", web_unit)
        if result == 0:
            web_alive = True
            services["active_web_unit"] = web_unit
            break
    if not web_alive:
        services["active_web_unit"] = "inactive"
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

    # Alert on purchase notifications that can be sent but are not moving.
    # Exclude unlinked/blocked Telegram recipients: those cannot be delivered
    # until the recipient connects/unblocks the bot, not a controller outage.
    delivery_sql = (
        "SELECT count(*) FROM telegram_notifications t "
        "WHERE t.kind='payment_approved' AND t.delivered_at IS NULL "
        "AND t.created_at < now() - interval '5 minutes' "
        "AND ((t.attempts = 0) "
        "OR (t.attempts >= 8 AND t.last_error IS NOT NULL "
        "AND t.last_error <> 'telegram link not found' "
        "AND t.last_error NOT ILIKE '%blocked by the user%') "
        "OR (t.last_error = 'telegram link not found' "
        "AND EXISTS (SELECT 1 FROM telegram_user_links l WHERE l.user_id=t.user_id)))"
    )
    delivery_code, delivery_value = run(
        "runuser", "-u", "postgres", "--", "psql", "-X", "-A", "-t",
        "-d", "twinpanel", "-c", delivery_sql, timeout=8,
    )
    pending_paid_attention = 0
    if delivery_code == 0:
        try:
            pending_paid_attention = int(delivery_value)
            if pending_paid_attention:
                errors.append("actionable_paid_telegram_deliveries_stalled")
        except ValueError:
            errors.append("telegram_paid_outbox_audit_parse_error")
    else:
        errors.append("telegram_paid_outbox_audit_unavailable")
    return {
        "event": "twinpanel_resilience_probe_v1",
        "healthy": not errors,
        "release": version,
        "active_web_port": port,
        "service_status": services,
        "stale_db_transactions": stale,
        "oldest_stale_seconds": max_age,
        "actionable_paid_delivery_pending": pending_paid_attention,
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
