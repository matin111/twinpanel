"""Capacity preflight for a one-service-per-subscriber Sudoku runtime."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.central_sudoku_capacity_v1 import (
    MAX_SUDOKU_STAGE_SERVICES, sudoku_port, capacity_report,
    assert_target_sudoku_capacity,
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

    def test_1900_users_pass_port_preflight_but_still_require_remote_ram(self):
        report=capacity_report(range(1,1901))
        self.assertTrue(report["ok"])
        self.assertTrue(report["node_runtime_admission_required"])
        self.assertEqual(report["eligible"],1900)

    def test_small_unambiguous_canary_passes_capacity_preflight(self):
        report=capacity_report(range(1,MAX_SUDOKU_STAGE_SERVICES+1))
        self.assertTrue(report["ok"])
        self.assertEqual(report["reason"],"CAPACITY_PRECHECK_OK")

    def test_stage_above_hard_limit_rejected(self):
        report=capacity_report(range(1,MAX_SUDOKU_STAGE_SERVICES+2))
        self.assertFalse(report["ok"])
        self.assertEqual(report["reason"],"TOO_MANY_PER_USER_SERVICES")

    def test_invalid_subscription_id_fails(self):
        with self.assertRaises(ValueError):
            sudoku_port(0)

class SudokuNodeResourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_target_with_3gb_free_rejects_1171_services(self):
        conn=MagicMock()
        conn.run=AsyncMock(return_value=SimpleNamespace(exit_status=0,stdout="3304128\n"))
        conn.wait_closed=AsyncMock()
        with patch("app.node_runtime_connection.connect_protocol_runtime",
                   new_callable=AsyncMock,return_value=conn):
            with self.assertRaisesRegex(RuntimeError,"SUDOKU_TARGET_MEMORY_ADMISSION_FAILED"):
                await assert_target_sudoku_capacity(MagicMock(),MagicMock(),range(1,1172))
        conn.close.assert_called_once()

    async def test_sufficient_ram_allows_canary(self):
        conn=MagicMock()
        conn.run=AsyncMock(return_value=SimpleNamespace(exit_status=0,stdout="6600000\n"))
        conn.wait_closed=AsyncMock()
        with patch("app.node_runtime_connection.connect_protocol_runtime",
                   new_callable=AsyncMock,return_value=conn):
            report=await assert_target_sudoku_capacity(MagicMock(),MagicMock(),[17,18])
        self.assertEqual(report["requested"],2)
        self.assertTrue(report["ok"])



if __name__=="__main__":
    unittest.main()
