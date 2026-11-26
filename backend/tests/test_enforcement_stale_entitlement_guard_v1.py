"""No stale quota command can revoke a renewed user or revive expired quota."""
from __future__ import annotations

import ast
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main

PATH=Path(__file__).resolve().parents[1]/"app/services/account_enforcement_v2.py"
TREE=ast.parse(PATH.read_text())
ACTIVE="ACTIVE"
_St=SimpleNamespace(ACTIVE=ACTIVE)
reasons=next(n for n in TREE.body if isinstance(n,ast.Assign) and any(
    isinstance(t,ast.Name) and t.id=="_STALE_REVOKE_REASONS" for t in n.targets
))
function=next(n for n in TREE.body if isinstance(n,ast.FunctionDef)
              and n.name=="_stale_enforcement_result")
ns={"SubscriptionStatus":_St,"datetime":datetime}
exec(compile(ast.fix_missing_locations(ast.Module(body=[reasons,function],type_ignores=[])),
             str(PATH),"exec"),ns)
test=ns["_stale_enforcement_result"]
now=datetime(2026,11,26,16,0,0)


def sub(status=ACTIVE,expires=None,limit=1000,used=300):
    return SimpleNamespace(status=status,expires_at=expires,
                           traffic_limit_bytes=limit,traffic_used_bytes=used)


class EntitlementCommandSafety(TestCase):
    def test_newly_renewed_active_user_old_revoke_ignored(self):
        for reason in ("scheduled_expiration","quota_exhausted",
                       "scheduled_quota_exhausted","reseller_manual_suspend"):
            self.assertEqual(test(sub(expires=now+timedelta(days=90)),
                                  "revoke_subscription",reason,now),
                             "controller_stale_revoke_skipped")

    def test_valid_unlimited_time_with_finite_volume(self):
        self.assertEqual(test(sub(expires=None,limit=900,used=899),
                              "revoke_subscription","quota_exhausted",now),
                         "controller_stale_revoke_skipped")
        self.assertIsNone(test(sub(expires=None,limit=900,used=900),
                               "revoke_subscription","quota_exhausted",now))

    def test_time_unlimited_and_volume_unlimited(self):
        x=sub(expires=None,limit=0,used=999999)
        self.assertIsNone(test(x,"restore_subscription","reserved_renewal",now))
        self.assertEqual(test(x,"revoke_subscription","scheduled_expiration",now),
                         "controller_stale_revoke_skipped")

    def test_expired_and_suspended_account_never_restored(self):
        for x in (sub(status="EXPIRED"),
                  sub(status="SUSPENDED"),sub(expires=now-timedelta(days=1)),
                  sub(limit=900,used=900)):
            self.assertEqual(test(x,"restore_subscription","reseller_pool_recharged",now),
                             "controller_stale_restore_skipped")

    def test_pool_and_node_scoped_revokes_not_overridden_by_global_state(self):
        x=sub()
        for reason in ("reseller_pool_exhausted","node_migrated",
                       "protocol_deactivated","subscription_create_postcondition_failed"):
            self.assertIsNone(test(x,"revoke_subscription",reason,now))

    def test_legacy_unstarted_duration_is_preserved(self):
        x=sub(expires=None)
        self.assertIsNone(test(x,"restore_subscription","reserved_renewal",now))
        self.assertIsNone(test(None,"revoke_subscription","subscription_hard_deleted",now))

    def test_executor_checks_before_ssh(self):
        execute=next(n for n in TREE.body if isinstance(n,ast.AsyncFunctionDef)
                     and n.name=="_execute_command")
        source=ast.unparse(execute)
        self.assertLess(source.index("_stale_enforcement_result("),
                        source.index("ssh_connect_saved("))
        self.assertIn("if not handled_by_central_sudoku:",source)
        claim=next(n for n in TREE.body if isinstance(n,ast.FunctionDef)
                   and n.name=="_claim_next_command")
        self.assertIn("'reason':",ast.unparse(claim))

if __name__=="__main__":
    main()
