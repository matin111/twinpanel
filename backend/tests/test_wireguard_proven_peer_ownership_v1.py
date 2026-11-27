#!/usr/bin/env python3
"""Fail-closed per-peer quota source tests with no database or network."""
from __future__ import annotations
import ast
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "app/services/wireguard_counter_ownership_v1.py"
spec = importlib.util.spec_from_file_location("tested_peer_ownership", MODULE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def address_peer(peers, address):
    for p in peers:
        if address in p.get("allowed_ips", ()):
            return p
    return None


def public_peer(peers, key):
    for p in peers:
        if p.get("public_key") == key:
            return p
    return None


def owner(sid, ip):
    return {"subscription_id": sid, "device_id": sid + 10000,
            "telemetry_identity": ip, "identity": ip}


def guard(devices, peers, *, records=None, cursors=None, protocol="wireguard",
          epoch="boot:A"):
    return m.select_proven_peer_devices(
        devices, peers, protocol=protocol,
        match_address=address_peer, match_public_key=public_peer,
        load_stored_public_key=(
            (lambda sid: records.get(sid)) if records is not None else None),
        cursor_owners=cursors, counter_epoch=epoch,
    )


class ProvenPeerOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.peers = [
            {"public_key": "pub-A", "allowed_ips": ["10.1.0.2/32"],
             "rx": 180, "tx": 350},
            {"public_key": "pub-B", "allowed_ips": ["10.1.0.3/32"],
             "rx": 90, "tx": 200},
            {"public_key": "pub-C", "allowed_ips": ["10.1.0.4/32"],
             "rx": 10, "tx": 20},
        ]
        self.conflict = [owner(1, "10.1.0.2/32"),
                         owner(2, "10.1.0.2/32"),
                         owner(3, "10.1.0.4/32")]

    def test_verified_public_keys_resolve_duplicate_stored_ip(self):
        devices, c = guard(self.conflict, self.peers,
                           records={1: "pub-A", 2: "pub-B"})
        self.assertEqual(len(devices), 3)
        self.assertEqual(c["verified_key_recovered"], 2)
        self.assertEqual(devices[0]["verified_runtime_public_key"], "pub-A")
        self.assertEqual(devices[1]["verified_runtime_public_key"], "pub-B")
        self.assertEqual(devices[1]["telemetry_identity"], "10.1.0.2/32")

    def test_missing_or_mismatched_key_skips_ambiguous_users(self):
        devices, c = guard(self.conflict, self.peers, records={1: "pub-A"})
        self.assertEqual([d["subscription_id"] for d in devices], [1, 3])
        self.assertEqual(c["unproven_identity_skipped"], 1)

    def test_no_stored_proof_never_charges_ambiguous_address(self):
        devices, c = guard(self.conflict, self.peers)
        self.assertEqual([d["subscription_id"] for d in devices], [3])
        self.assertEqual(c["unproven_identity_skipped"], 2)

    def test_same_verified_public_key_still_fails_closed(self):
        devices, c = guard(self.conflict, self.peers,
                           records={1: "pub-A", 2: "pub-A"})
        self.assertEqual([d["subscription_id"] for d in devices], [3])
        self.assertEqual(c["shared_peer_skipped"], 2)

    def test_unverified_source_never_inherits_another_users_bytes(self):
        devices, c = guard(self.conflict, self.peers,
                           records={1: "pub-Z", 2: "pub-B"})
        self.assertEqual([d["subscription_id"] for d in devices], [2, 3])
        self.assertEqual(c["unproven_identity_skipped"], 1)

    def test_bad_decryption_fails_closed(self):
        def damaged(_sid):
            raise RuntimeError("secret cannot decrypt")
        devices, c = m.select_proven_peer_devices(
            self.conflict, self.peers, protocol="wireguard",
            match_address=address_peer, match_public_key=public_peer,
            load_stored_public_key=damaged)
        self.assertEqual([d["subscription_id"] for d in devices], [3])
        self.assertEqual(c["unproven_identity_skipped"], 2)

    def test_cursor_owned_by_other_subscriber_rejected(self):
        row = {"subscription_id": 777, "device_id": 999, "protocol": "wireguard",
               "counter_epoch": "boot:A", "last_uplink_value": 0,
               "last_downlink_value": 0}
        devices, c = guard([owner(1, "10.1.0.2/32")], self.peers,
                           cursors={"wireguard:pub-A": row})
        self.assertEqual(devices, [])
        self.assertEqual(c["cursor_owner_conflict_skipped"], 1)

    def test_same_epoch_decreasing_counter_rejected(self):
        row = {"subscription_id": 1, "device_id": 10001,
               "protocol": "wireguard", "counter_epoch": "boot:A",
               "last_uplink_value": 181, "last_downlink_value": 350}
        devices, c = guard([owner(1, "10.1.0.2/32")], self.peers,
                           cursors={"wireguard:pub-A": row})
        self.assertFalse(devices)
        self.assertEqual(c["counter_regression_skipped"], 1)

    def test_epoch_change_only_allows_core_ledger_to_decide(self):
        row = {"subscription_id": 1, "device_id": 10001,
               "protocol": "wireguard", "counter_epoch": "boot:old",
               "last_uplink_value": 999, "last_downlink_value": 999}
        devices, c = guard([owner(1, "10.1.0.2/32")], self.peers,
                           cursors={"wireguard:pub-A": row})
        self.assertEqual(len(devices), 1)
        self.assertEqual(c["counter_regression_skipped"], 0)

    def test_unchanged_unique_ip_remains_eligible(self):
        unique = [owner(3, "10.1.0.4/32")]
        devices, c = guard(unique, self.peers)
        self.assertIs(devices[0], unique[0])
        self.assertEqual(c["safe_devices"], 1)

    def test_wrong_protocol_rejected(self):
        with self.assertRaises(ValueError):
            guard([], [], protocol="sudoku")

    def test_guard_executes_before_batches_and_canonical_uses_key(self):
        code = (ROOT / "app/services/modern_quota_runtime_v314.py").read_text()
        start = code.index("def _apply_collected_node_runtime_batched(")
        self.assertLess(code.index("select_proven_peer_devices(", start),
                        code.index("for offset in range(0, len(devices),", start))
        ledger = (ROOT / "app/services/modern_quota_runtime_v257.py").read_text()
        self.assertIn('device.get("verified_runtime_public_key")', ledger)
        ast.parse(ledger)

if __name__ == "__main__":
    unittest.main()
