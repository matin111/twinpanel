"""Retired Sudoku per-subscriber bulk adapter (compatibility stubs only).

All Sudoku enrollment and revocation belong to the shared V2 runtime.
This module deliberately contains no remote installer source, SSH calls or
systemd service creation code. Keep the public names for existing imports
while rejecting obsolete operations before touching the network or database.

Do not restore the V1 per-customer unit writer: it creates thousands of
twinpanel-sudoku-sub-N units and conflicts with central runtime ownership.
"""
from __future__ import annotations

from typing import Any

from .services.central_sudoku_capacity_v1 import (
    MAX_LEGACY_SUDOKU_SERVICES, sudoku_port,
)


def verify_accounts(accounts: list[dict]) -> None:
    if not isinstance(accounts,list) or not 1<=len(accounts)<=MAX_LEGACY_SUDOKU_SERVICES:
        raise ValueError("SUDOKU_BULK_CAPACITY_EXCEEDED")
    ids=set(); ports=set()
    for item in accounts:
        if not isinstance(item,dict):
            raise ValueError("SUDOKU_BULK_INVALID_ROW")
        sid=item.get("subscription_id")
        port=item.get("port")
        master=item.get("master_public")
        if not isinstance(sid,int) or sid<=0 or sid in ids:
            raise ValueError("SUDOKU_BULK_INVALID_ID")
        if type(port) is not int or port!=sudoku_port(sid) or port in ports:
            raise ValueError("SUDOKU_BULK_INVALID_PORT")
        if not isinstance(master,str) or not 32<=len(master)<=512 or any(c not in "0123456789abcdefABCDEF" for c in master):
            raise ValueError("SUDOKU_BULK_INVALID_PUBLIC_KEY")
        ids.add(sid);ports.add(port)


def remote_source(*, base="/etc/twinpanel/standalone/sudoku/subscriptions",
                  unit_dir="/etc/systemd/system",
                  program="/usr/local/bin/twinpanel-sudoku") -> str:
    """No remote Sudoku V1 installer may be generated, even for a dry run."""
    raise RuntimeError("SUDOKU_LEGACY_BULK_DISABLED_USE_SHARED_V2")


async def apply_bulk(conn: Any, accounts: list[dict]) -> dict:
    """Reject obsolete bulk writes before SSH, credentials, or systemd."""
    raise RuntimeError("SUDOKU_LEGACY_BULK_DISABLED_USE_SHARED_V2")
