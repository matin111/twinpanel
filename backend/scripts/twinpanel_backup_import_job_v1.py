"""Standalone verifier for authenticated chunked backup imports."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.backup_chunk_import_v1 import run_import_job
if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit(2)
    run_import_job(sys.argv[1])
