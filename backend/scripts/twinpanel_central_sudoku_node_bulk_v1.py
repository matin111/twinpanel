#!/usr/bin/env python3
"""Retired Sudoku V1 per-subscriber staging command.

Shared Sudoku V2 convergence is the only supported enrollment path. Keep this
legacy script as a fail-closed compatibility entry point: no DB reads, locks,
key generation, SSH calls, credential mutations or systemd modifications.
Even a V1 "dry run" must not use a stale per-user plan.
"""
from __future__ import annotations

import argparse
import asyncio
import json


RETIRED = "SUDOKU_LEGACY_STAGE_RETIRED_USE_SHARED_V2"


def args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-id", type=int, required=True)
    parser.add_argument("--limit", type=int, default=3000)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-node-id", type=int)
    return parser.parse_args(argv)


async def stage(node_id: int, limit: int, apply: bool):
    """Never resume the obsolete single-listener-per-customer workflow."""
    raise RuntimeError(RETIRED)


if __name__ == "__main__":
    parsed = args()
    print("CENTRAL_SUDOKU_SAFE_STOP", json.dumps({
        "error_type": "RetiredLegacyStage",
        "code": RETIRED,
    }, separators=(",", ":")), flush=True)
    raise SystemExit(2)
