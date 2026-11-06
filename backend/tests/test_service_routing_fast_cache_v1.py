"""Regression: tunnel routing verification may never spawn per-rule checks."""
import ast
from pathlib import Path

source = Path(__file__).resolve().parents[1] / "app/service_routing_stability_v139.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
block = next(
    ast.literal_eval(node.value)
    for node in tree.body
    if isinstance(node, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "_AGENT_ROUTING_V139" for t in node.targets)
)
routing_tree = ast.parse(block)
required = {
    "_service_routing_live_snapshot",
    "_service_routing_matches",
    "_service_routing_restore",
}
selected = [
    node for node in routing_tree.body
    if isinstance(node, ast.FunctionDef) and node.name in required
]
assert len(selected) == 3
ns = {"_SERVICE_ROUTING_CHAINS": (("filter", "TP_FWD"),), "_SERVICE_ROUTING_VERIFIED_SNAPSHOT": None}
exec(compile(ast.Module(body=selected, type_ignores=[]), "<agent>", "exec"), ns)

calls = []
live_rules = ["-N TP_FWD", "-A TP_FWD -j ACCEPT"]
def ipt(table, *args):
    calls.append(args[0])
    assert args[0] == "-S", "Never run one iptables -C per rule"
    return 0, "\n".join(live_rules)

ns["ipt"] = ipt
desired = {("filter", "TP_FWD"): [("-j", "ACCEPT")]}

# Unverified cold-start rules may not be trusted, even with matching counts.
assert not ns["_service_routing_matches"](desired)
assert calls == ["-S"]

stages = []
ns["_service_routing_restore_script"] = lambda desired: "valid restore script"
ns["_service_routing_run_restore"] = lambda script, *, test_only: stages.append((script, test_only))
calls.clear()
ns["_service_routing_restore"](desired)
assert stages == [("valid restore script", True), ("valid restore script", False)]
assert calls == ["-S"]
calls.clear()
assert ns["_service_routing_matches"](desired)
assert calls == ["-S"], "stable rules must be verified with one chain snapshot"

# Same-count kernel tampering is rejected with one snapshot; no subprocess scan.
live_rules[-1] = "-A TP_FWD -j DROP"
calls.clear()
assert not ns["_service_routing_matches"](desired)
assert calls == ["-S"]

# On drift, a new validated atomic restore creates a fresh trusted snapshot.
live_rules[-1] = "-A TP_FWD -j ACCEPT"
calls.clear()
assert not ns["_service_routing_matches"](desired), "cache must be invalidated after drift"
assert calls == ["-S"]
ns["_service_routing_restore"](desired)
assert ns["_service_routing_matches"](desired)

# Changes to desired rule counts fail closed without per-rule checks.
desired[("filter", "TP_FWD")].append(("-j", "ACCEPT"))
calls.clear()
assert not ns["_service_routing_matches"](desired)
assert calls == ["-S"]
print("SERVICE_ROUTING_VERIFIED_SNAPSHOT_V140=PASS")
