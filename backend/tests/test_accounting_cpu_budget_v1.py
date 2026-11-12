"""Account for the multi-process CPU cgroup without starving small hosts."""
from __future__ import annotations
import importlib.util
import unittest
from pathlib import Path
from unittest import mock

SCRIPT=Path(__file__).resolve().parents[1]/"scripts/twinpanel_accounting_cpu_budget_v1.py"
spec=importlib.util.spec_from_file_location("cpu_budget",SCRIPT)
cpu=importlib.util.module_from_spec(spec)
spec.loader.exec_module(cpu)

class AccountingCPUBudgetTests(unittest.TestCase):
    def test_adaptive_headroom(self):
        self.assertEqual(cpu.target_percent(1),75)
        self.assertEqual(cpu.target_percent(2),75)
        self.assertEqual(cpu.target_percent(4),100)
        self.assertEqual(cpu.target_percent(8),200)
        self.assertEqual(cpu.target_percent(16),250)
        self.assertEqual(cpu.target_percent(48),250)

    def test_adaptive_target_must_reduce_oversized_persistent_quota(self):
        with mock.patch.object(cpu,"run",side_effect=["active","4s"]):
            with mock.patch.object(cpu.os,"sched_getaffinity",return_value=set(range(16))):
                status=cpu.inspect()
        self.assertEqual(status["target_quota_percent"],250)
        self.assertTrue(status["needs_adjustment"])
        self.assertFalse(status["needs_increase"])

    def test_systemd_durations_and_unlimited(self):
        self.assertEqual(cpu.parse_current("750ms"),75)
        self.assertEqual(cpu.parse_current("1.500000s"),150)
        self.assertEqual(cpu.parse_current("4s"),400)
        self.assertIsNone(cpu.parse_current("infinity"))
        with self.assertRaises(RuntimeError):
            cpu.parse_current("bad")

    def test_apply_does_not_restart_or_reduce_quota(self):
        with mock.patch.object(cpu.os,"geteuid",return_value=0), \
             mock.patch.object(cpu,"inspect",return_value={
               "service_active":True,"needs_increase":False,"needs_adjustment":False,
               "target_quota_percent":250}), \
             mock.patch.object(cpu,"run",side_effect=AssertionError("no mutation")):
            self.assertFalse(cpu.apply()["needs_increase"])

    def test_only_increases_in_place(self):
        before={"service_active":True,"needs_increase":True,"needs_adjustment":True,"target_quota_percent":250}
        after={"service_active":True,"needs_increase":False,"needs_adjustment":False,"target_quota_percent":250}
        with mock.patch.object(cpu.os,"geteuid",return_value=0), \
             mock.patch.object(cpu,"inspect",side_effect=[before,after]), \
             mock.patch.object(cpu,"run",return_value="") as command:
            self.assertFalse(cpu.apply()["needs_increase"])
        command.assert_called_once_with([
            "systemctl","set-property","twinpanel-modern-accounting.service","CPUQuota=250%"])

if __name__=="__main__":
    unittest.main()
