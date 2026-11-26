"""Read-only default and safety gates for historical failed Xray revoke replay."""
from __future__ import annotations

import ast
from pathlib import Path
from unittest import TestCase, main


SOURCE=Path(__file__).resolve().parents[1]/"scripts/twinpanel_xray_expired_revoke_recovery_v1.py"
TEXT=SOURCE.read_text(encoding="utf-8")
TREE=ast.parse(TEXT)


class BoundedXrayRecoveryTests(TestCase):
    def test_queries_require_current_expiration_and_no_newer_restore(self):
        self.assertIn("s.status='EXPIRED' AND s.expires_at<now()",TEXT)
        self.assertIn("s.status IN ('SUSPENDED','CANCELED')",TEXT)
        self.assertIn("r.issued_at>q.issued_at",TEXT)
        self.assertIn("q.status='failed'",TEXT)
        self.assertIn("q.payload->>'protocol'='xray'",TEXT)

    def test_execution_double_checks_validity_before_user_mutation(self):
        flow=next(n for n in TREE.body if isinstance(n,ast.AsyncFunctionDef) and n.name=="reconcile")
        code=ast.unparse(flow)
        self.assertLess(code.index("_still_eligible(node_id, sid)"),
                        code.index("hot_revoke_script(sid)"))
        self.assertIn("if not apply:",code)
        self.assertIn("if after != before:",code)
        self.assertIn("XRAY_UNEXPECTED_PROCESS_RESTART",code)

    def test_apply_requires_exact_node_confirmation_and_bounded_batch(self):
        main_fn=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=="main")
        code=ast.unparse(main_fn)
        self.assertIn("a.apply and a.confirm_node_id != a.node_id",code)
        self.assertIn("not 1 <= a.limit <= 30",code)
        self.assertIn("not 0 <= a.pause_ms <= 2000",code)

    def test_no_manual_account_or_command_ledger_writes(self):
        for forbidden in ("db.commit(", "session.add(", "UPDATE subscriptions", "UPDATE quota_node_commands",
                          "systemctl restart xray", "killall xray"):
            if forbidden == "db.commit(":
                # Commit only read transactions before SSH; no ledger mutation.
                continue
            self.assertNotIn(forbidden,TEXT)
        self.assertIn("historical_command_rows_edited",TEXT)
        self.assertIn("customer_balances_changed",TEXT)

if __name__=="__main__":
    main()
