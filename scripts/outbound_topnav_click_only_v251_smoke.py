#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "components/ui.tsx"
SOURCE = UI.read_text(encoding="utf-8")

# Outbound must use the same mounted topnav contents as every other Admin page
# so shared runtime widgets such as SystemReleaseFooter can preload status and
# surface update attention consistently.
assert 'const clickOnlyTopnav=active==="/admin/outbounds";' not in SOURCE
assert '{(!clickOnlyTopnav||groupOpen)&&<div className="topnav-menu">' not in SOURCE
assert '<div className="topnav-menu">' in SOURCE
assert 'open={groupOpen}' in SOURCE
assert 'setOpenGroup(current=>current===group.en?null:group.en);' in SOURCE
assert 'group.en==="System & Maintenance"' in SOURCE
assert '<SystemReleaseFooter/>' in SOURCE

print("OUTBOUND_TOPNAV_SHARED_RUNTIME_V251_SMOKE=PASS")
