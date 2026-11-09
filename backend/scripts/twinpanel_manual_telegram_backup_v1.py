"""Standalone worker for administrator-triggered Telegram-only backups."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from app.manual_telegram_backup_v1 import run_manual_job

if __name__ == "__main__":
    if len(sys.argv)!=2:
        raise SystemExit(2)
    run_manual_job(sys.argv[1])
