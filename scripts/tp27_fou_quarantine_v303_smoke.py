#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUARANTINE = ROOT / "backend/app/tp27_fou_quarantine_v303.py"
MANAGER = ROOT / "backend/app/tunnel_transport_manager_v12.py"
API = ROOT / "backend/app/tp27_repair_api_v265.py"
V265 = ROOT / "backend/app/tp27_self_repair_v265.py"
TP27_FAST = ROOT / "backend/app/transport_candidates/tp27_fast.py"


def read(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    ast.parse(text, filename=str(path))
    return text


q = read(QUARANTINE)
manager = read(MANAGER)
api = read(API)
v265 = read(V265)
tp27_fast = read(TP27_FAST)

# Root-cause fixture: rc.302 candidate order starts with 443 and then 8443.
assert "FOU_PORT_CANDIDATES = (443, 8443, 2053, 2083, 10443)" in tp27_fast

# Existing V265 safety policy remains unchanged.
assert "FAILURE_THRESHOLD = 3" in v265
assert "REPAIR_COOLDOWN_SECONDS = 180" in v265
assert "ports = [int(value) for value in tp27_fast.FOU_PORT_CANDIDATES]" in v265
assert "ports = [value for value in ports if value != current_port] + [current_port]" in v265

# V303 is soft quarantine, not candidate removal.
assert 'MARKER = "TWINPANEL_TP27_FOU_QUARANTINE_V303"' in q
assert "SOFT_QUARANTINE_SECONDS = 24 * 60 * 60" in q
assert 'state.get("fou_port_failures")' in q
assert 'state.get("attempts")' in q  # backward compatibility for V265 rows
assert 'str(attempt.get("result") or "").strip().lower() != "failed"' in q
assert 'state["fou_port_failures"]' in q
assert 'state["fou_port_quarantine_seconds"] = SOFT_QUARANTINE_SECONDS' in q
assert 'state["fou_port_ordering_version"] = 303' in q
assert "return fresh + quarantined + current + non_fou" in q
assert "failures.pop(port, None)" in q  # successful full probe clears stale memory

# The wrapper must patch V265's ordering and both success/failure persistence.
assert "v265._attempt_order = _attempt_order" in q
assert "v265._repair_meta = _repair_meta" in q
assert "v265._failed_repair_meta = _failed_repair_meta" in q

# Automatic manager and manual API repair must share one ordering policy.
assert "from .tp27_fou_quarantine_v303 import apply_tp27_fou_quarantine_v303" in manager
assert "apply_tp27_fou_quarantine_v303()" in manager
assert '"tp27_fou_quarantine=v303 "' in manager

assert "from .tp27_fou_quarantine_v303 import apply_tp27_fou_quarantine_v303" in api
assert "apply_tp27_fou_quarantine_v303()" in api
assert "fou_quarantine=v303" in api

# Policy activation must happen before the background repair task is created.
assert manager.index("apply_tp27_fou_quarantine_v303()") < manager.index(
    "tp27_self_repair_task = asyncio.create_task("
)

# API activation must happen before TP27 routes are attached/used.
assert api.index("apply_tp27_fou_quarantine_v303()") < api.index(
    '@router.get(\n        "/{tunnel_id}/tp27/diagnose"'
)

print("TP27 FOU QUARANTINE V303 SMOKE PASS")
