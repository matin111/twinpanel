"""Regression: stable Agent route rules must avoid per-rule iptables subprocesses."""
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
selected = [
    node for node in routing_tree.body
    if isinstance(node, ast.FunctionDef) and node.name == "_service_routing_matches"
]
globals_ = [
    node for node in routing_tree.body
    if isinstance(node, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "_SERVICE_ROUTING_VERIFIED_SNAPSHOT" for t in node.targets)
]
assert len(selected) == 1 and len(globals_) == 1
ns = {"_SERVICE_ROUTING_CHAINS": (("filter", "TP_FWD"),)}
exec(compile(ast.Module(body=globals_ + selected, type_ignores=[]), "<agent>", "exec"), ns)

calls = []
live_rules = ["-N TP_FWD", "-A TP_FWD -j ACCEPT"]
def ipt(table, *args):
    calls.append(args[0])
    if args[0] == "-S":
        return 0, "\n".join(live_rules)
    if args[0] == "-C":
        return (0, "") if live_rules[-1].endswith("ACCEPT") else (1, "rule missing")
    raise AssertionError("unexpected command")
ns["ipt"] = ipt
desired = {("filter", "TP_FWD"): [("-j", "ACCEPT")]}
assert ns["_service_routing_matches"](desired)
assert calls == ["-S"], "exact live rule match should avoid first per-rule -C"
calls.clear()
assert ns["_service_routing_matches"](desired)
assert calls == ["-S"], "stable rules must not spawn per-rule -C processes"

# A changed live chain must cause full verification and never accept a stale cache.
live_rules[-1] = "-A TP_FWD -j DROP"
calls.clear()
assert not ns["_service_routing_matches"](desired)
assert calls == ["-S", "-C"], "live rule drift must fail closed"
live_rules[-1] = "-A TP_FWD -j ACCEPT"
calls.clear()
assert ns["_service_routing_matches"](desired)
assert calls == ["-S"], "exact restored live rules should avoid per-rule -C"
calls.clear()
assert ns["_service_routing_matches"](desired)
assert calls == ["-S"]
desired[("filter", "TP_FWD")].append(("-j", "ACCEPT"))
calls.clear()
assert not ns["_service_routing_matches"](desired), "different desired count must fail"
assert "-C" not in calls, "count mismatch must fail safely before expensive checks"
print("SERVICE_ROUTING_VERIFIED_SNAPSHOT_V1=PASS")
