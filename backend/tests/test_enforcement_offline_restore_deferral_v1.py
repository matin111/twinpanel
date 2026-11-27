"""An offline node must not burn restore SSH attempts but revokes never defer."""
from __future__ import annotations

import ast
from enum import Enum
from pathlib import Path
from unittest import TestCase, main

SOURCE=Path(__file__).resolve().parents[1]/"app/services/account_enforcement_v2.py"
TREE=ast.parse(SOURCE.read_text())
FUNC=next(node for node in TREE.body if isinstance(node,ast.FunctionDef)
          and node.name=="_should_defer_offline_restore")


def pure_gate():
    module=ast.Module(body=[
        ast.ImportFrom(module="__future__",names=[ast.alias(name="annotations")],level=0),
        FUNC,
    ],type_ignores=[])
    ns={}
    exec(compile(ast.fix_missing_locations(module),str(SOURCE),"exec"),ns)
    return ns["_should_defer_offline_restore"]


class NodeStatus(Enum):
    ONLINE="ONLINE"
    OFFLINE="OFFLINE"


class OfflineRestoreDeferralTests(TestCase):
    def test_restore_offline_is_deferred_but_revoke_never_is(self):
        guard=pure_gate()
        self.assertTrue(guard("restore_subscription",NodeStatus.OFFLINE))
        self.assertTrue(guard("restore_subscription","OFFLINE"))
        self.assertTrue(guard("restore_subscription","UNKNOWN"))
        self.assertFalse(guard("restore_subscription",NodeStatus.ONLINE))
        for value in (NodeStatus.ONLINE,NodeStatus.OFFLINE,"UNKNOWN"):
            self.assertFalse(guard("revoke_subscription",value))

    def test_stale_entitlement_is_checked_before_offline_node_deferral(self):
        fn=next(n for n in TREE.body if isinstance(n,ast.AsyncFunctionDef) and n.name=="_execute_command")
        code=ast.unparse(fn)
        self.assertIn("elif _should_defer_offline_restore(command_type, node.status)",code)
        self.assertLess(
            code.index("_stale_enforcement_result("),
            code.index("_should_defer_offline_restore(command_type, node.status)"),
        )
        self.assertIn('result_code = stale_result',code)

    def test_deferred_command_never_acknowledges_or_uses_attempt_budget(self):
        fn=next(n for n in TREE.body if isinstance(n,ast.AsyncFunctionDef) and n.name=="_execute_command")
        code=ast.unparse(fn)
        start=code.index("if isinstance(error, ControllerNodeOfflinePending)")
        end=code.index("if isinstance(error, CentralSudokuReconciliationPending)",start)
        segment=code[start:end]
        for expected in (
            "row.status = 'controller_processing'",
            "row.attempt_count = max(0, int(row.attempt_count or 0) - 1)",
            "row.last_delivered_at = now",
            "row.result_code = 'controller_offline_restore_waiting'",
            "status_db.commit()",
        ):
            self.assertIn(expected,segment)
        self.assertNotIn("row.status = 'succeeded'",segment)
        self.assertNotIn("ssh_connect_saved",segment)

    def test_no_mutation_of_entitlement_ledger_in_offline_gate(self):
        source=ast.unparse(FUNC)
        for forbidden in ("db.", "traffic_used_bytes =", "expires_at =", "status_db."):
            self.assertNotIn(forbidden,source)


if __name__=="__main__":
    main()
