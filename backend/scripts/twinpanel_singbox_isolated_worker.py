#!/usr/bin/env python3
"""Dedicated sing-box online and byte accounting, isolated from heavy V314.

Uses existing authenticated node API, quota rules, watermark and counter
semantics. Does not create/change VPN credentials, ports or node services.
The existing /run/twinpanel-singbox-quota-v265.lock prevents double writers.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services import singbox_native_accounting_v265 as singbox
from app.services.accounting_device_map_batch_v1 import (
    install_accounting_device_batch_cache,
)

# Preserve the 45-second ceiling configured by the parent. Each sweep may
# take longer, but unlike the legacy shared event loop it cannot be starved
# by SQLAlchemy work in the WireGuard/TrustTunnel/Sudoku collector.
singbox.SINGBOX_ACCOUNTING_INTERVAL_SECONDS = 45.0
install_accounting_device_batch_cache()


if __name__ == "__main__":
    print("TWINPANEL_SINGBOX_PROCESS_ISOLATION_V1_ACTIVE", flush=True)
    asyncio.run(singbox.singbox_native_accounting_loop())
