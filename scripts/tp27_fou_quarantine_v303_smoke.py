#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUARANTINE = ROOT / "backend/app/tp27_fou_quarantine_v303.py"
GUARD = ROOT / "backend/app/tp27_underlay_fault_domain_v306.py"
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
guard = read(GUARD)
manager = read(MANAGER)
api = read(API)
v265 = read(V265)
tp27_fast = read(TP27_FAST)

# Candidate universe stays bounded and V303 continues to reorder that universe.
assert "FOU_PORT_CANDIDATES = (443, 8443, 2053, 2083, 10443)" in tp27_fast
assert "ports = [int(value) for value in tp27_fast.FOU_PORT_CANDIDATES]" in v265
assert "ports = [value for value in ports if value != current_port] + [current_port]" in v265

# V304 remains the carrier anti-flap owner. V306 is an additive fault-domain
# overlay and must not rewrite these already accepted thresholds.
assert literal_assignment(v265, "STABILITY_REVISION") == 304
assert literal_assignment(v265, "STRUCTURAL_FAILURE_THRESHOLD") == 2
assert literal_assignment(v265, "PATH_FAILURE_THRESHOLD") == 8
assert literal_assignment(v265, "REPAIR_COOLDOWN_SECONDS") == 900
assert "FAILURE_THRESHOLD =" not in q
assert "STRUCTURAL_FAILURE_THRESHOLD =" not in q
assert "PATH_FAILURE_THRESHOLD =" not in q
assert "REPAIR_COOLDOWN_SECONDS =" not in q
assert "STRUCTURAL_FAILURE_THRESHOLD =" not in guard
assert "PATH_FAILURE_THRESHOLD =" not in guard
assert "REPAIR_COOLDOWN_SECONDS =" not in guard

# V303 remains soft quarantine, not candidate removal.
assert 'MARKER = "TWINPANEL_TP27_FOU_QUARANTINE_V303"' in q
assert "SOFT_QUARANTINE_SECONDS = 24 * 60 * 60" in q
assert 'state.get("fou_port_failures")' in q
assert 'state.get("attempts")' in q
assert 'str(attempt.get("result") or "").strip().lower() != "failed"' in q
assert 'state["fou_port_failures"]' in q
assert 'state["fou_port_quarantine_seconds"] = SOFT_QUARANTINE_SECONDS' in q
assert 'state["fou_port_ordering_version"] = 303' in q
assert "return fresh + quarantined + current + non_fou" in q
assert "failures.pop(port, None)" in q

# V306 owns pair-scoped underlay fault classification.
assert 'MARKER = "TWINPANEL_TP27_UNDERLAY_FAULT_DOMAIN_V306"' in guard
assert literal_assignment(guard, "VERSION") == 306
assert literal_assignment(guard, "UNDERLAY_PING_COUNT") == 5
assert literal_assignment(
    guard,
    "MAX_HEALTHY_UNDERLAY_PACKET_LOSS_PCT",
) == 20.0
assert "contextvars.ContextVar" in guard
assert "healthy_sibling_tunnels" in guard
assert '"underlay_suspected"' in guard
assert '"underlay_pair"' in guard
assert '"structural_carrier"' in guard
assert '"dataplane"' in guard
assert '"pair_corroborated"' in guard
assert '"repair_suppressed"' in guard
assert '"replacement_recommended"' in guard
assert "tp27_underlay_degraded:" in guard
assert "carrier_rebuild=suppressed;" in guard
assert 'normalized_source == "manager"' in guard
assert 'v265._failure_cycles[' in guard
assert '"reason": "underlay_pair_degraded"' in guard

# The policy is pair-scoped: a healthy sibling on the same Iran node
# corroborates that the shared Iran node is not globally broken.
assert "v265.Tunnel.iran_node_id == int(tunnel.iran_node_id)" in guard
assert 'v265.TunnelTransport.status == "online"' in guard
assert "v265.TunnelTransport.last_error.is_(None)" in guard
assert "Node.status" not in guard
assert '.status = "offline"' not in guard

# V306 patches only V265 module globals. This preserves explicit API repair
# function objects while manager reconcile sees the underlay repair fence.
for contract in (
    "v265.tunnel_nodes = _tunnel_nodes",
    "v265._diagnose_with_connections = _diagnose_with_connections",
    "v265._diagnosis_error = _diagnosis_error",
    "v265._diagnosis_failure_kind = _diagnosis_failure_kind",
    "v265.repair_tp27 = _manager_safe_repair_tp27",
):
    assert contract in guard

# V303 still patches ordering/persistence and then activates V306.
assert "v265._attempt_order = _attempt_order" in q
assert "v265._repair_meta = _repair_meta" in q
assert "v265._failed_repair_meta = _failed_repair_meta" in q
assert "from .tp27_underlay_fault_domain_v306 import (" in q
assert "apply_tp27_underlay_fault_domain_v306()" in q
assert q.index("v265._failed_repair_meta = _failed_repair_meta") < q.index(
    "apply_tp27_underlay_fault_domain_v306()"
)
assert q.index("apply_tp27_underlay_fault_domain_v306()") < q.index(
    "_applied = True"
)

# Automatic manager and manual API still share V303 activation, which now
# activates V306 in both process types without changing their public routes.
assert "from .tp27_fou_quarantine_v303 import apply_tp27_fou_quarantine_v303" in manager
assert "apply_tp27_fou_quarantine_v303()" in manager
assert '"tp27_fou_quarantine=v303 "' in manager

assert "from .tp27_fou_quarantine_v303 import apply_tp27_fou_quarantine_v303" in api
assert "apply_tp27_fou_quarantine_v303()" in api
assert "fou_quarantine=v303" in api

assert manager.index("apply_tp27_fou_quarantine_v303()") < manager.index(
    "tp27_self_repair_task = asyncio.create_task("
)
assert api.index("apply_tp27_fou_quarantine_v303()") < api.index(
    '@router.get(\n        "/{tunnel_id}/tp27/diagnose"'
)

print("TP27 FOU QUARANTINE V303 + UNDERLAY FAULT DOMAIN V306 COMPAT SMOKE PASS")
