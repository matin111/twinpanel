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


def literal_assignment(source: str, name: str):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id == name:
                    if node.value is None:
                        raise AssertionError(f"assignment has no value: {name}")
                    return ast.literal_eval(node.value)
    raise AssertionError(f"assignment not found: {name}")


q = read(QUARANTINE)
manager = read(MANAGER)
api = read(API)
v265 = read(V265)
tp27_fast = read(TP27_FAST)

# Candidate universe stays bounded and V303 continues to reorder that universe.
assert "FOU_PORT_CANDIDATES = (443, 8443, 2053, 2083, 10443)" in tp27_fast
assert "ports = [int(value) for value in tp27_fast.FOU_PORT_CANDIDATES]" in v265
assert "ports = [value for value in ports if value != current_port] + [current_port]" in v265

# V304 now owns the anti-flap thresholds. V303 must consume V265/V304 helpers
# without overriding those policy constants itself.
assert literal_assignment(v265, "STABILITY_REVISION") == 304
assert literal_assignment(v265, "STRUCTURAL_FAILURE_THRESHOLD") == 2
assert literal_assignment(v265, "PATH_FAILURE_THRESHOLD") == 8
assert literal_assignment(v265, "REPAIR_COOLDOWN_SECONDS") == 900
assert "FAILURE_THRESHOLD =" not in q
assert "STRUCTURAL_FAILURE_THRESHOLD =" not in q
assert "PATH_FAILURE_THRESHOLD =" not in q
assert "REPAIR_COOLDOWN_SECONDS =" not in q

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

print("TP27 FOU QUARANTINE V303 + V304 COMPAT SMOKE PASS")
