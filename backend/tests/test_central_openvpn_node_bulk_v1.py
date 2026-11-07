"""Central OpenVPN staging safety contracts."""
import unittest
from unittest.mock import MagicMock, patch

from app.models import NodeStatus, NodeType
from scripts import twinpanel_central_openvpn_node_bulk_v1 as bulk


class CentralOpenVPNTests(unittest.TestCase):
    def _node(self):
        node = MagicMock()
        node.retired_at = None
        node.node_type = NodeType.EXIT
        node.status = NodeStatus.ONLINE
        node.show_to_users = False
        node.enable_openvpn = True
        return node

    def test_disabled_central_pki_never_falls_back_to_per_user_easyrsa(self):
        db = MagicMock()
        db.get.return_value = self._node()
        cfg = MagicMock()
        cfg.status = "online"
        db.query.return_value.filter_by.return_value.one_or_none.return_value = cfg
        with patch.object(bulk, "is_openvpn_central_pki_enabled", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "CENTRAL_PKI_REQUIRED"):
                bulk.validate_node(db, 14)

    def test_published_node_is_rejected_even_with_central_pki(self):
        db = MagicMock()
        node = self._node()
        node.show_to_users = True
        db.get.return_value = node
        with self.assertRaisesRegex(RuntimeError, "HIDDEN_ONLINE"):
            bulk.validate_node(db, 14)

    def test_apply_requires_exact_node_confirmation(self):
        with self.assertRaises(SystemExit):
            bulk.parse_args(["--node-id", "14", "--apply"])
        parsed = bulk.parse_args([
            "--node-id", "14", "--apply", "--confirm-node-id", "14"])
        self.assertTrue(parsed.apply)


if __name__ == "__main__":
    unittest.main()
