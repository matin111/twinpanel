"""The real node installer must run central desired-state apply BEFORE publish.

These source-contract checks target the actual /install-background-v1 handler,
not an unused helper route or a simulated successful workflow.
"""
from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.routers import publish_node_all_users_v1 as installer
from app.routers import publish_node_all_users_v2 as central_publish
from app.services import node_stage_publish_guard_v1 as guard


class NewNodeInstallerCutoverTests(unittest.TestCase):
    def test_real_install_background_uses_runtime_engine_before_publish(self):
        src=inspect.getsource(installer._install_node_in_background)
        self.assertIn("central_stage.run",src)
        self.assertIn("asyncio.to_thread(",src)
        self.assertLess(
            src.index("stage_rc = await asyncio.to_thread("),
            src.index("publish_result = await publish_node_to_all_users("),
        )
        self.assertIn('if stage_rc != 0:',src)
        self.assertIn('"CENTRAL_RUNTIME_COVERAGE_INCOMPLETE"',src)
        self.assertNotIn("enqueue_node_backfill(",src)
        self.assertNotIn('and fabric.get("ok") is not False',src)

    def test_real_installer_publishes_through_audited_v2_handler(self):
        self.assertIs(installer.publish_node_to_all_users,
                      central_publish.publish_node_to_all_users_v2)

    def test_only_verified_enrollment_coverage_can_publish(self):
        class Query:
            def filter(self,*a,**kw):return self
            def order_by(self,*a,**kw):return self
            def first(self):return SimpleNamespace(stage="enrolling_users")
        class Db:
            def query(self,*a,**kw):return Query()
        with patch.object(guard,"require_staged_node_publish_ready",wraps=guard.require_staged_node_publish_ready):
            with patch("app.central_node_stage_audit_v1.verify_coverage",
                       return_value={"ok":False}):
                with self.assertRaises(HTTPException) as err:
                    guard.require_staged_node_publish_ready(Db(),14)
                self.assertEqual(err.exception.status_code,409)
            with patch("app.central_node_stage_audit_v1.verify_coverage",
                       return_value={"ok":True}):
                guard.require_staged_node_publish_ready(Db(),14)


if __name__=="__main__":
    unittest.main()
