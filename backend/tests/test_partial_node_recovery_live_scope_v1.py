"""Recover a hidden 15/16 Exit without forcing a full 16-listener gate."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from app.models import NodeStatus, NodeType
from app.routers.publish_node_all_users_v2 import reverify_and_stage_existing_exit_v1

class PartialRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_xray_tls_allows_scoped_live_reverify(self):
        db=MagicMock()
        node=SimpleNamespace(
            id=27, retired_at=None, node_type=NodeType.EXIT,
            status=NodeStatus.ONLINE, show_to_users=False,
            enable_v2ray=False,
        )
        job=SimpleNamespace(
            stage="failed", state="failed",
            error_code="XRAY_NEW_EXIT_TLS_CERTIFICATE_NOT_READY",
            installed_protocols=15, expected_protocols=16,
            users_assigned=None,
        )
        db.get.return_value=node
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value=job
        db.query.return_value.filter.return_value.all.return_value=[]
        admission={"eligible_users":2}
        with (
            patch("app.services.new_node_readiness_v1.verify_new_exit_readiness",
                  new_callable=AsyncMock, return_value={
                      "ok": True, "ready_count":15, "missing":["v2ray"],
                      "ready_protocols":["openvpn","wireguard"],
                  }) as health,
            patch("app.services.central_progressive_exit_admission_v1.admit_verified_exit",
                  return_value=admission) as admit,
            patch("app.services.central_node_stage_launcher_v1.launch",
                  return_value={"scheduled":True,"unit":"ci-safe"}),
        ):
            result=await reverify_and_stage_existing_exit_v1(27,db=db)
        health.assert_awaited_once_with(
            db, 27, require_tls_profiles=True, allow_partial=True,
        )
        admit.assert_called_once_with(db,27)
        self.assertEqual(result["live_protocols"],15)
        self.assertEqual(result["users_assigned"],2)
        self.assertEqual(job.error_code,"PARTIAL_PROTOCOLS_PENDING")
        self.assertEqual(job.state,"completed")
        self.assertTrue(node.show_to_users is False or node.show_to_users is True)

if __name__=="__main__":
    unittest.main()
