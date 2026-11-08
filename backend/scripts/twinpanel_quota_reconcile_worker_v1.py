#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

RESULT_PREFIX = "TWINPANEL_QUOTA_PROCESS_RESULT_V1="


def _lower_priority() -> None:
    try:
        os.nice(10)
    except (AttributeError, OSError):
        pass


def _changed_items(result: dict) -> list[dict]:
    return [
        item
        for item in result.get("nodes", [])
        if (
            item.get("opened")
            or item.get("closed")
            or item.get("usage_events")
        )
    ]


async def _main() -> int:
    from app.services.quota_runtime_reconcile import reconcile_quota_runtime_once
    from app.services.l2tp_quota_runtime_v113 import (
        reconcile_l2tp_quota_runtime_once,
    )

    changed: list[dict] = []
    errors: list[dict] = []

    # OpenVPN is now owned by the independent 30-second fast observer in
    # quota_process_isolation_v1. Never run two simultaneous OpenVPN writers:
    # the heavy sweep remains for L2TP and Cisco/Xray only.
    collectors = (
        ("l2tp", reconcile_l2tp_quota_runtime_once),
        ("cisco_xray", reconcile_quota_runtime_once),
    )

    for name, reconcile in collectors:
        started = asyncio.get_running_loop().time()
        print("QUOTA_COLLECTOR_START", name, flush=True)
        try:
            result = await reconcile()
            changed.extend(_changed_items(result))
            node_results = result.get("nodes", []) if isinstance(result, dict) else []
            node_errors = [
                {"node_id": item.get("node_id"), "error": str(item.get("error") or "")[:240]}
                for item in node_results
                if item.get("ok") is False
            ]
            for item in node_errors:
                errors.append({"collector": name, **item})
            print(
                "QUOTA_COLLECTOR_DONE", name,
                "seconds", round(asyncio.get_running_loop().time() - started, 2),
                "nodes", len(node_results),
                "errors", len(node_errors),
                flush=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            errors.append(
                {
                    "collector": name,
                    "error": f"{type(exc).__name__}:{str(exc)[:500]}",
                }
            )

    payload = {
        "ok": not errors,
        "changed": changed,
        "errors": errors,
    }
    print(
        RESULT_PREFIX
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    _lower_priority()
    raise SystemExit(asyncio.run(_main()))
