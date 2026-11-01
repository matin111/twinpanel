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
    from app.services.openvpn_quota_runtime_v106 import (
        reconcile_openvpn_quota_runtime_once,
    )
    from app.services.l2tp_quota_runtime_v113 import (
        reconcile_l2tp_quota_runtime_once,
    )

    changed: list[dict] = []
    results: dict[str, dict] = {}
    errors: list[dict] = []

    collectors = (
        ("cisco_xray", reconcile_quota_runtime_once),
        ("openvpn", reconcile_openvpn_quota_runtime_once),
        ("l2tp", reconcile_l2tp_quota_runtime_once),
    )

    for name, reconcile in collectors:
        try:
            result = await reconcile()
            results[name] = result
            changed.extend(_changed_items(result))
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
        "results": results,
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
