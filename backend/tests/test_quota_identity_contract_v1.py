"""Regression tests for the canonical 16-source quota attribution boundary."""
from __future__ import annotations

from unittest import TestCase, main

from app.protocol_account_registry import ALL_PROTOCOL_KEYS
from app.quota_identity_contract_v1 import quota_device_matches_protocol


class QuotaIdentityGuardTests(TestCase):
    def test_every_protocol_accepts_its_own_source(self):
        self.assertEqual(len(ALL_PROTOCOL_KEYS), 16)
        for name in ALL_PROTOCOL_KEYS:
            with self.subTest(name=name):
                self.assertTrue(quota_device_matches_protocol(name, name))

    def test_cisco_and_xray_node_aliases_match_credentials(self):
        self.assertTrue(quota_device_matches_protocol("cisco", "openconnect"))
        self.assertTrue(quota_device_matches_protocol("v2ray", "xray"))
        self.assertTrue(quota_device_matches_protocol("naive", "naiveproxy"))

    def test_cross_protocol_device_id_must_not_bill_another_protocol(self):
        for source in ALL_PROTOCOL_KEYS:
            for other in ALL_PROTOCOL_KEYS:
                if source != other:
                    with self.subTest(source=source, reported=other):
                        self.assertFalse(quota_device_matches_protocol(source, other))

    def test_unknown_or_missing_protocol_is_not_authenticated(self):
        self.assertFalse(quota_device_matches_protocol("shadowtls", ""))
        self.assertFalse(quota_device_matches_protocol("shadowtls", "unknown"))
        self.assertFalse(quota_device_matches_protocol("", "shadowtls"))


if __name__ == "__main__":
    main()
