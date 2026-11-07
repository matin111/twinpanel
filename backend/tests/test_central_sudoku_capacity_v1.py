"""Capacity preflight for a one-service-per-subscriber Sudoku runtime."""
from __future__ import annotations

import unittest

from app.services.central_sudoku_capacity_v1 import (
    MAX_LEGACY_SUDOKU_SERVICES, sudoku_port, capacity_report,
)


class SudokuCapacityTests(unittest.TestCase):
    def test_matches_existing_standalone_port_algorithm(self):
        self.assertEqual(sudoku_port(1), 30000)
        self.assertEqual(sudoku_port(30000), 59999)
        self.assertEqual(sudoku_port(30001), 30000)

    def test_port_collision_rejected_even_for_two_eligible_users(self):
        report=capacity_report([1,30001])
        self.assertFalse(report["ok"])
        self.assertEqual(report["reason"],"PORT_COLLISION")
        self.assertEqual(report["port_collisions"],1)

    def test_unvalidated_thousands_of_services_are_rejected(self):
        report=capacity_report(range(1,1901))
        self.assertFalse(report["ok"])
        self.assertEqual(report["reason"],"TOO_MANY_PER_USER_SERVICES")
        self.assertEqual(report["eligible"],1900)

    def test_small_unambiguous_canary_passes_capacity_preflight(self):
        report=capacity_report(range(1,MAX_LEGACY_SUDOKU_SERVICES+1))
        self.assertTrue(report["ok"])
        self.assertEqual(report["reason"],"CAPACITY_PRECHECK_OK")

    def test_invalid_subscription_id_fails(self):
        with self.assertRaises(ValueError):
            sudoku_port(0)


if __name__=="__main__":
    unittest.main()
