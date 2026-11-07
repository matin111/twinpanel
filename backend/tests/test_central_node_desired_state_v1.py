"""Source-of-truth tests: controller state, not per-user SSH/queue."""
from __future__ import annotations

import unittest

from app.services.central_node_desired_state_v1 import (
    build_desired_state, require_valid_desired_state,
)


class DesiredNodeStateTests(unittest.TestCase):
    def test_one_snapshot_deduplicates_migrated_and_new_customers(self):
        state = build_desired_state(
            14, [3, 2, 3, 1],
            [(1, "openvpn"), (1, "wireguard"), (2, "v2ray"),
             (3, "sudoku"), (3, "sudoku"), (999, "v2ray")],
        )
        self.assertEqual(state.subscription_ids, (1, 2, 3))
        self.assertEqual(state.pair_count, 4)
        self.assertEqual(state.counts_by_protocol(), {
            "openvpn": 1, "sudoku": 1, "v2ray": 1, "wireguard": 1,
        })
        self.assertEqual(state.invalid_protocols, ())
        self.assertEqual(state.without_entitlements, ())
        self.assertIs(require_valid_desired_state(state), state)

    def test_same_desired_state_has_same_fingerprint_despite_order(self):
        first = build_desired_state(14, [5, 1], [(5, "v2ray"), (1, "cisco")])
        second = build_desired_state(14, [1, 5], [(1, "cisco"), (5, "v2ray")])
        self.assertEqual(first.fingerprint, second.fingerprint)
        changed = build_desired_state(14, [1, 5], [(1, "cisco"), (5, "openvpn")])
        self.assertNotEqual(first.fingerprint, changed.fingerprint)

    def test_revocation_and_expiry_reflected_by_central_snapshot(self):
        before = build_desired_state(
            14, [1, 2], [(1, "cisco"), (2, "v2ray")],
        )
        after = build_desired_state(14, [2], [(1, "cisco"), (2, "v2ray")])
        self.assertEqual(after.entitled_pairs, ((2, "v2ray"),))
        self.assertNotEqual(before.fingerprint, after.fingerprint)

    def test_unentitled_and_unknown_protocols_fail_closed(self):
        missing = build_desired_state(14, [1, 2], [(1, "cisco")])
        self.assertEqual(missing.without_entitlements, (2,))
        with self.assertRaisesRegex(RuntimeError, "WITHOUT_PROTOCOLS"):
            require_valid_desired_state(missing)
        unknown = build_desired_state(14, [1], [(1, "not-a-vpn")])
        with self.assertRaisesRegex(RuntimeError, "UNKNOWN"):
            require_valid_desired_state(unknown)

    def test_explicit_node_target_and_subscriber_limit(self):
        with self.assertRaises(ValueError):
            build_desired_state(0, [1], [(1, "cisco")])
        over = build_desired_state(14, range(1, 4),
                                   [(i, "cisco") for i in range(1, 4)])
        with self.assertRaisesRegex(RuntimeError, "CAPACITY"):
            require_valid_desired_state(over, max_users=2)


if __name__ == "__main__":
    unittest.main()
