#!/usr/bin/env python3
"""Supervised node installer; survives API process restarts and updater reloads.

No SSH password is accepted in argv, environment or logging. A 0600 /run
payload is opened and unlinked immediately. The node-specific systemd unit
owns the complete operation; API is only the initial dispatcher/status reader.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.getLogger("asyncssh").setLevel(logging.WARNING)


def _scope_from_origin(origin: str) -> dict:
    parsed = urlsplit(origin or "")
    scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "https"
    host = parsed.netloc
    if (not host or len(host) > 253
            or not re.fullmatch(r"[A-Za-z0-9.:-]+", host)):
        host = "127.0.0.1:8095"
    return {
        "type": "http", "method": "POST", "scheme": scheme,
        "path": "/v1/nodes/install-background-v1",
        "raw_path": b"/v1/nodes/install-background-v1",
        "root_path": "", "query_string": b"",
        "headers": [(b"host", host.encode("ascii"))],
        "server": ("127.0.0.1", 8095),
        "client": ("127.0.0.1", 0),
    }


def main(argv=None) -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--job-id",required=True)
    parser.add_argument("--resume-node-id",type=int,default=0)
    parser.add_argument("--publish",choices=["0","1"],default="0")
    args=parser.parse_args(argv)

    from app.services.durable_node_install_launcher_v1 import consume_secret_job
    from app.routers.publish_node_all_users_v1 import (
        BackgroundNodeInstallIn, _install_node_in_background,
        _safe_install_progress,
    )

    try:
        if args.resume_node_id:
            if args.resume_node_id<1:
                raise RuntimeError("NODE_INSTALL_RESUME_NODE_INVALID")
            from app.services.hidden_exit_install_resume_v1 import resume_hidden_exit
            asyncio.run(resume_hidden_exit(
                node_id=args.resume_node_id,
                job_id=args.job_id,
                publish_to_all_users=args.publish=="1",
            ))
        else:
            entry=consume_secret_job(args.job_id)
            payload=BackgroundNodeInstallIn.model_validate(entry["payload"])
            scope=_scope_from_origin(str(entry.get("origin") or ""))
            asyncio.run(_install_node_in_background(payload,scope,args.job_id))
    except Exception as exc:
        from app.services.node_os_preflight_v1 import safe_node_install_error_code
        code=safe_node_install_error_code(exc)
        if code == "NODE_INSTALL_UNEXPECTED_ERROR":
            code="NODE_INSTALL_WORKER_FAILED"
        _safe_install_progress(args.job_id,"failed",error_code=code)
        print("NODE_INSTALL_DETACHED_WORKER_FAILED",{
            "job_id":str(args.job_id),"error_type":type(exc).__name__,
            "error_code":code,
        },flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
