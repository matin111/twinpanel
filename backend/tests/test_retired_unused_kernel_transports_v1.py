"""Regression guard: retire unused TP6/IPIP without suppressing live VXLAN.

Source-only/API tests; never install, remove or change active tunnels.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.routers.modern_transports import (
    RETIRED_UNUSED_CANDIDATES, install_modern_transport, transport_catalog,
)


async def main():
    assert RETIRED_UNUSED_CANDIDATES == {"tp6_fast", "kernel_ipip"}
    names = {str(row["transport"]) for row in transport_catalog()["transports"]}
    assert not (names & RETIRED_UNUSED_CANDIDATES)
    assert "kernel_vxlan" in names
    print("RETIRED_UNUSED_TRANSPORT_CATALOG_PASS")

    for name in RETIRED_UNUSED_CANDIDATES:
        try:
            await install_modern_transport(tunnel_id=6, transport=name, db=None)
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError(f"retired transport install allowed: {name}")
    print("RETIRED_UNUSED_INSTALL_BLOCK_PASS")

    ui=(Path(__file__).resolve().parents[2]/"components/smart-transports-runtime-v26.tsx").read_text()
    assert 'RETIRED_UNUSED_CARRIERS=new Set(["tp6_fast","kernel_ipip"])' in ui
    assert 'name!=="kernel_vxlan"||normalized(status)!=="not_installed"' in ui
    print("INSTALLED_KERNEL_VXLAN_REMAINS_VISIBLE_PASS")


if __name__ == "__main__":
    asyncio.run(main())
