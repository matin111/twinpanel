"""Out-of-request selected tunnel provisioning. Launched as a transient systemd unit.

Never execute this script through an HTTP worker or on the Iran node.
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app.routers.tunnel_selected_jobs_v1 import run_job

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit(2)
    run_job(sys.argv[1])
