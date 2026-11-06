"""Fast kernel-snapshot route verification regressions (no root or iptables)."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/app/service_routing_stability_v139.py"
module = ast.parse(SOURCE.read_text(encoding="utf-8"))
agent_source = next(
    node.value.value for node in module.body
    if isinstance(node, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "_AGENT_ROUTING_V139" for t in node.targets)
)
agent_ast = ast.parse(agent_source)
names = {
    "_service_routing_live_snapshot",
    "_service_routing_matches",
    "_service_routing_restore",
}
functions = [node for node in agent_ast.body if isinstance(node, ast.FunctionDef) and node.name in names]
assert len(functions) == len(names)


class RouteSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.chains = (("nat", "TP_DNAT"), ("filter", "TP_FWD"))
        self.desired = {
            ("nat", "TP_DNAT"): [("-p", "tcp", "--dport", "24007", "-j", "ACCEPT")],
            ("filter", "TP_FWD"): [("-j", "ACCEPT")],
        }
        self.live = {
            ("nat", "TP_DNAT"): "-N TP_DNAT\n-A TP_DNAT -p tcp -m tcp --dport 24007 -j ACCEPT\n",
            ("filter", "TP_FWD"): "-N TP_FWD\n-A TP_FWD -j ACCEPT\n",
        }
        self.actions = []

        def ipt(table, action, chain, *args):
            self.actions.append((table, action, chain))
            if action != "-S":
                raise AssertionError("Per-rule iptables subprocess forbidden")
            return 0, self.live[(table, chain)]

        self.ctx = {
            "_SERVICE_ROUTING_CHAINS": self.chains,
            "_SERVICE_ROUTING_VERIFIED_SNAPSHOT": None,
            "ipt": ipt,
        }
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"), self.ctx)

    def test_cold_start_does_not_run_n_per_rule_checks(self):
        self.assertFalse(self.ctx["_service_routing_matches"](self.desired))
        self.assertEqual(len(self.actions), 2)
        self.assertTrue(all(action == "-S" for _, action, _ in self.actions))

    def test_atomic_restore_trusts_verified_kernel_snapshot(self):
        stage = []
        self.ctx["_service_routing_restore_script"] = lambda desired: "verified-input"
        self.ctx["_service_routing_run_restore"] = lambda script, *, test_only: stage.append((script, test_only))
        self.ctx["_service_routing_restore"](self.desired)
        self.assertEqual(stage, [("verified-input", True), ("verified-input", False)])
        self.assertTrue(self.ctx["_service_routing_matches"](self.desired))
        self.assertEqual(len(self.actions), 4)

    def test_same_count_rule_tampering_invalidates_cache(self):
        self.ctx["_service_routing_restore_script"] = lambda desired: "verified-input"
        self.ctx["_service_routing_run_restore"] = lambda script, *, test_only: None
        self.ctx["_service_routing_restore"](self.desired)
        self.live[("nat", "TP_DNAT")] = self.live[("nat", "TP_DNAT")].replace("24007", "24008")
        self.assertFalse(self.ctx["_service_routing_matches"](self.desired))

    def test_desired_rule_drift_invalidates_cache(self):
        self.ctx["_service_routing_restore_script"] = lambda desired: "verified-input"
        self.ctx["_service_routing_run_restore"] = lambda script, *, test_only: None
        self.ctx["_service_routing_restore"](self.desired)
        other = dict(self.desired)
        other[("filter", "TP_FWD")] = [("-j", "REJECT")]
        self.assertFalse(self.ctx["_service_routing_matches"](other))

    def test_missing_rule_fails_closed(self):
        self.ctx["_service_routing_restore_script"] = lambda desired: "verified-input"
        self.ctx["_service_routing_run_restore"] = lambda script, *, test_only: None
        self.ctx["_service_routing_restore"](self.desired)
        self.live[("nat", "TP_DNAT")] = "-N TP_DNAT\n"
        self.assertFalse(self.ctx["_service_routing_matches"](self.desired))

    def test_all_existing_nodes_get_new_rollout_marker(self):
        code = SOURCE.read_text(encoding="utf-8")
        self.assertIn('AGENT_MARKER = "TWINPANEL_SERVICE_ROUTING_FAST_SNAPSHOT_V140"', code)
        self.assertIn("# TWINPANEL_SERVICE_ROUTING_FAST_SNAPSHOT_V140", agent_source)
        self.assertIn("rollout._AGENT_MARKER = (", code)


if __name__ == "__main__":
    unittest.main()
