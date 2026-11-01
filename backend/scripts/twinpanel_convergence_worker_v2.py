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

RESULT_PREFIX = "TWINPANEL_CONVERGENCE_PROCESS_RESULT_V2="


def _lower_priority() -> None:
    try:
        os.nice(10)
    except (AttributeError, OSError):
        pass


async def _main() -> int:
    from app import node_subscription_convergence_v114 as runtime

    result = await runtime.reconcile_installed_exit_nodes_once()
    print(
        RESULT_PREFIX
        + json.dumps(
            result,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    _lower_priority()
    raise SystemExit(asyncio.run(_main()))
