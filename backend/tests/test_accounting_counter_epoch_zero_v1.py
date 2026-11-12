"""Cumulative counter resets must not write zero-byte ledger events."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from app.services import modern_quota_runtime_v257 as meter


class CounterEpochZeroTests(TestCase):
    def setUp(self):
        self.db=MagicMock()
        self.cursor=SimpleNamespace(
            subscription_id=7,device_id=12,protocol="trusttunnel",
            counter_epoch="old-runtime-epoch",last_uplink_value=0,
            last_downlink_value=0,last_sequence=1,updated_at=None)
        self.db.query.return_value.filter.return_value.first.return_value=self.cursor
        self.arguments=dict(
            db=self.db,node_id=29,
            device={"device_id":12,"subscription_id":7,"identity":"test"},
            protocol="trusttunnel",source_key="trusttunnel:test",
            counter_epoch="new-runtime-epoch",uplink=0,downlink=0,
            session_key=None,client_ip=None,reported_at=datetime.now(timezone.utc))

    def test_zero_epoch_reset_updates_cursor_without_ledger_write(self):
        with patch.object(meter,"apply_usage_event") as usage:
            result=meter._baseline_or_apply_cumulative(**self.arguments)
        self.assertTrue(result["baselined"])
        self.assertTrue(result["epoch_changed"])
        self.assertFalse(result["event"])
        self.assertEqual(result["accepted_bytes"],0)
        self.assertEqual(self.cursor.counter_epoch,"new-runtime-epoch")
        self.assertEqual(self.cursor.last_uplink_value,0)
        self.assertEqual(self.cursor.last_downlink_value,0)
        usage.assert_not_called()

    def test_positive_counters_after_reset_are_still_billed(self):
        meter._baseline_or_apply_cumulative(**self.arguments)
        new_args={**self.arguments,"uplink":47,"downlink":53}
        with patch.object(meter,"apply_usage_event",return_value={"accepted_bytes":100}) as usage, \
             patch.object(meter,"_activate_from_real_usage_if_needed"):
            result=meter._baseline_or_apply_cumulative(**new_args)
        self.assertTrue(result["event"])
        self.assertEqual(result["accepted_bytes"],100)
        usage.assert_called_once()


if __name__=="__main__":
    main()
