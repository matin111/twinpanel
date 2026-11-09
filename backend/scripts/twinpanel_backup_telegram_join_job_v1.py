"""Background worker verifying and importing individually uploaded Telegram parts."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.backup_telegram_part_import_v1 import join_job
if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit(2)
    join_job(sys.argv[1])
