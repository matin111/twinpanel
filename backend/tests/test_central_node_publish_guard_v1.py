"""Staged new-Exit publish must not activate the legacy per-user queue."""
from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from app.models import NodeType
from app.routers.publish_node_all_users_v2 import publish_node_to_all_users_v2


def staged_db():
    db=MagicMock()
    node=SimpleNamespace(id=14,name="New Exit",node_type=NodeType.EXIT,
                         retired_at=None,show_to_users=False)
    node_query=MagicMock()
    node_query.filter.return_value.filter.return_value.first.return_value=node
    job_query=MagicMock()
    job_query.filter.return_value.order_by.return_value.first.return_value=(
        SimpleNamespace(stage="verified_ready")
    )
    db.query.side_effect=[node_query,job_query]
    db.execute.return_value.rowcount=0
    return db,node


class CentralPublishSafetyTests(unittest.TestCase):
    def test_staged_incomplete_credentials_reject_publish_before_sql(self):
        db,node=staged_db()
        with (patch("app.services.node_stage_publish_guard_v1.require_staged_node_publish_ready"),
              patch("app.central_node_stage_audit_v1.verify_coverage",
                    return_value={"ok":False,"missing_protocol_pairs":7,
                                  "missing_node_memberships":0})):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(publish_node_to_all_users_v2(14,db=db))
        self.assertEqual(raised.exception.status_code,409)
        self.assertFalse(node.show_to_users)
        db.execute.assert_not_called()
        db.commit.assert_not_called()

    def test_verified_central_staging_never_enqueues_legacy_queue(self):
        db,node=staged_db()
        with (patch("app.services.node_stage_publish_guard_v1.require_staged_node_publish_ready"),
              patch("app.central_node_stage_audit_v1.verify_coverage",
                    return_value={"ok":True}),
              patch("app.routers.publish_node_all_users_v2.enqueue_node_backfill") as queue):
            result=asyncio.run(publish_node_to_all_users_v2(14,db=db))
        self.assertTrue(node.show_to_users)
        self.assertTrue(result["central_coverage_verified"])
        self.assertFalse(result["backfill"]["queued"])
        queue.assert_not_called()
        db.commit.assert_called_once()


if __name__=="__main__":
    unittest.main()
