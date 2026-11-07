"""New Exit visibility is fail-closed at creation and staged PATCH."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from fastapi import HTTPException
from app.models import NodeType
from app.schemas import NodeCreate, NodeUpdate
from app.routers.nodes import create_node, update_node


class NewExitVisibilityTests(unittest.TestCase):
    def test_registration_forces_new_exit_hidden(self):
        db=MagicMock()
        db.query.return_value.filter.return_value.first.return_value=None
        db.query.return_value.filter.return_value.filter.return_value.first.return_value=None
        payload=NodeCreate(name="New-Hidden-Exit",node_type=NodeType.EXIT,
                           public_ip="203.0.113.15",show_to_users=True)
        node=create_node(payload,db=db)
        self.assertFalse(node.show_to_users)
        db.commit.assert_called_once()

    def test_existing_iran_node_does_not_force_hide(self):
        db=MagicMock()
        db.query.return_value.filter.return_value.first.return_value=None
        db.query.return_value.filter.return_value.filter.return_value.first.return_value=None
        payload=NodeCreate(name="New-Iran",node_type=NodeType.IRAN,
                           public_ip="203.0.113.14",show_to_users=True)
        node=create_node(payload,db=db)
        self.assertTrue(node.show_to_users)

    def test_direct_visibility_toggle_blocks_unstaged_credentials(self):
        db=MagicMock()
        node=SimpleNamespace(id=14,retired_at=None,
                             show_to_users=False,public_ip="203.0.113.12")
        node_query=MagicMock()
        node_query.filter.return_value.first.return_value=node
        progress_query=MagicMock()
        progress_query.filter.return_value.order_by.return_value.first.return_value=(
            SimpleNamespace(stage="verified_ready")
        )
        db.query.side_effect=[node_query,progress_query]
        with (patch("app.services.node_stage_publish_guard_v1.require_staged_node_publish_ready"),
              patch("app.central_node_stage_audit_v1.verify_coverage",
                    return_value={"ok":False})):
            with self.assertRaises(HTTPException) as blocked:
                update_node(14,NodeUpdate(show_to_users=True),db=db)
        self.assertEqual(blocked.exception.status_code,409)
        self.assertFalse(node.show_to_users)
        db.commit.assert_not_called()


if __name__=="__main__":
    unittest.main()
