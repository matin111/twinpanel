#!/usr/bin/env python3
"""Parser tests: the dual-carrier canary must only accept valid lab probes."""
import unittest
from udp_redundant_canary import PREFIX, parse_seq

class TestRedundantCanaryParser(unittest.TestCase):
    def valid(self, sequence):
        return PREFIX + sequence.to_bytes(4, "big") + b"Z" * 224

    def test_round_trip_sequence(self):
        self.assertEqual(parse_seq(self.valid(299)),299)
        self.assertEqual(parse_seq(self.valid(0)),0)

    def test_reject_unknown_payload(self):
        self.assertIsNone(parse_seq(b"non-canary-vpn-packet"))

    def test_reject_truncated_payload(self):
        self.assertIsNone(parse_seq(self.valid(52)[:-1]))

    def test_reject_extended_payload(self):
        self.assertIsNone(parse_seq(self.valid(52)+b"x"))

if __name__=="__main__":
    unittest.main()