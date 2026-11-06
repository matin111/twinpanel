"""Central modern node-lookup safety contracts."""
import os
import unittest
from unittest.mock import MagicMock, patch

from app.services.central_modern_connection_lookup_v1 import (
    applied_modern_connection, central_modern_delivery_enabled,
)


class CentralLookupContracts(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(central_modern_delivery_enabled())
            db = MagicMock()
            self.assertIsNone(applied_modern_connection(db, "anytls", 22))
            db.query.assert_not_called()

    def test_v2ray_never_uses_modern_lookup(self):
        with patch.dict(os.environ, {"TWINPANEL_CENTRAL_MODERN_DELIVERY_V1": "true"}):
            db = MagicMock()
            self.assertIsNone(applied_modern_connection(db, "v2ray", 22))
            db.query.assert_not_called()

    def test_invalid_node_id_rejected_without_query(self):
        with patch.dict(os.environ, {"TWINPANEL_CENTRAL_MODERN_DELIVERY_V1": "true"}):
            db = MagicMock()
            self.assertIsNone(applied_modern_connection(db, "anytls", "bad"))
            db.query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
