#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "components/ui.tsx"
SOURCE = UI.read_text(encoding="utf-8")

assert 'const clickOnlyTopnav=active==="/admin/outbounds";' in SOURCE
assert '{(!clickOnlyTopnav||groupOpen)&&<div className="topnav-menu">' in SOURCE
assert 'open={groupOpen}' in SOURCE
assert 'setOpenGroup(current=>current===group.en?null:group.en);' in SOURCE

# The fix must remain scoped to the Outbound page. Other admin routes keep the
# existing navigation behavior unless they explicitly opt into this contract.
assert SOURCE.count('active==="/admin/outbounds"') == 1

print("OUTBOUND_TOPNAV_CLICK_ONLY_V251_SMOKE=PASS")
