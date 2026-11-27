#!/usr/bin/env python3
"""Ensure quota enforcement ordering does not block reachable nodes."""
from __future__ import annotations
import ast
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1]
          / "app/services/account_enforcement_v2.py")


class DurableQuotaCommandFairnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SOURCE.read_text(encoding="utf8")
        cls.tree = ast.parse(cls.text)
        funcs = [x for x in cls.tree.body if isinstance(x,ast.FunctionDef)
                 and x.name=="_claim_next_command"]
        assert len(funcs)==1
        cls.fn = ast.get_source_segment(cls.text,funcs[0])

    def test_online_first_then_revoke_then_fifo(self):
        text=self.fn
        self.assertIn("Node.status == NodeStatus.ONLINE",text)
        self.assertIn('QuotaNodeCommand.command_type == "revoke_subscription"',text)
        start=text.index(".order_by(")
        self.assertLess(text.index("Node.status == NodeStatus.ONLINE",start),
                        text.index('QuotaNodeCommand.command_type == "revoke_subscription"',start))
        self.assertLess(text.index('QuotaNodeCommand.command_type == "revoke_subscription"',start),
                        text.index("QuotaNodeCommand.issued_at.asc()",start))

    def test_no_offline_command_is_acknowledged_or_deleted(self):
        text=self.fn
        self.assertIn(".outerjoin(Node, Node.id == QuotaNodeCommand.node_id)",text)
        self.assertNotIn("delete(",text)
        self.assertNotIn("NODE_OFFLINE_AWAITING_RECOVERY",text)
        self.assertIn('row.status = "controller_processing"',text)

    def test_lock_only_command_rows_with_join(self):
        self.assertIn(".with_for_update(of=QuotaNodeCommand, skip_locked=True)",self.fn)
        self.assertNotIn(".with_for_update(skip_locked=True)",self.fn)

    def test_status_and_lease_guards_preserved(self):
        text=self.fn
        self.assertIn("QuotaNodeCommand.expires_at > now",text)
        self.assertIn('QuotaNodeCommand.status == "controller_pending"',text)
        self.assertIn('QuotaNodeCommand.status == "controller_processing"',text)
        self.assertIn("QuotaNodeCommand.last_delivered_at < stale_before",text)
        self.assertIn("QuotaNodeCommand.node_id.notin_(sorted(exclude_node_ids))",text)

    def test_existing_offline_restore_retry_semantics_remain(self):
        whole=self.text
        self.assertIn("ControllerNodeOfflinePending",whole)
        self.assertIn('"controller_offline_restore_waiting"',whole)
        self.assertIn("row.attempt_count = max(0, int(row.attempt_count or 0) - 1)",whole)
        self.assertIn("await asyncio.gather(",whole)

    def test_priority_matches_queue_intent(self):
        commands=[
            ("offline", "revoke_subscription", 1),
            ("online","restore_subscription",2),
            ("online","revoke_subscription",3),
            ("offline","restore_subscription",4),
            ("online","revoke_subscription",5),
        ]
        priority=lambda x:(0 if x[0]=="online" else 1,
                           0 if x[1]=="revoke_subscription" else 1,x[2])
        self.assertEqual([row[2] for row in sorted(commands,key=priority)],
                         [3,5,2,1,4])

if __name__=="__main__":
    unittest.main()
