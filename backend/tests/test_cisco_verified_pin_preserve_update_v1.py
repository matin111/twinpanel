"""Keep trusted Cisco server certificate pin across source-based updates."""
import unittest
from types import SimpleNamespace
from app.routers.account_delivery import _cisco_trusted_pin_for_client
from app.runtime_settings_model import RuntimeSetting


class StubDb:
    def __init__(self, value):
        self.value = value
        self.lookups = []

    def get(self, model, key):
        self.lookups.append((model, key))
        if self.value is None:
            return None
        return SimpleNamespace(setting_value=self.value)


class CiscoPinnedCertTests(unittest.TestCase):
    def test_returns_verified_pin_only_for_selected_node(self):
        value = "pin-sha256:" + "A" * 43 + "="
        db = StubDb(value)
        self.assertEqual(_cisco_trusted_pin_for_client(db, 27), value)
        self.assertEqual(db.lookups, [(RuntimeSetting, "cisco.trusted_servercert.node.27")])

    def test_missing_pin_uses_existing_behavior(self):
        self.assertIsNone(_cisco_trusted_pin_for_client(StubDb(None), 27))
        self.assertIsNone(_cisco_trusted_pin_for_client(StubDb(""), 27))

    def test_invalid_certificate_pin_must_not_be_exposed(self):
        for value in ("sha256:abc", "pin-sha256:invalid", "pin-sha256:" + "Z" * 44,
                      "pin-sha256:" + "A" * 43 + "= injected"):
            with self.subTest(value=value[:22]):
                self.assertIsNone(_cisco_trusted_pin_for_client(StubDb(value), 27))


if __name__ == "__main__":
    unittest.main()
