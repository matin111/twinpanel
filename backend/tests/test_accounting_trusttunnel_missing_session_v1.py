"""TrustTunnel meter must not crash or fabricate bytes for absent users."""
from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from app.services import modern_quota_runtime_v257 as collector


class TrustTunnelAbsentUserTests(TestCase):
    def test_missing_inactive_user_skips_without_false_usage(self):
        db=MagicMock()
        db.query.return_value.filter.return_value.distinct.return_value.all.return_value=[]
        devices=[{"device_id":17,"identity":"absent","subscription_id":42}]
        with patch.object(collector,"_mark_presence") as presence, \
             patch.object(collector,"_baseline_or_apply_cumulative") as meter:
            result=collector._apply_trusttunnel(
                db,node=SimpleNamespace(id=31),devices=devices,
                epoch="valid-epoch",rows=[])
        self.assertEqual(result["matched"],0)
        self.assertEqual(result["accepted_bytes"],0)
        self.assertEqual(result["usage_events"],0)
        presence.assert_not_called()
        meter.assert_not_called()
        db.query.assert_called_once()

    def test_missing_previously_active_user_closes_only_existing_session(self):
        db=MagicMock()
        db.query.return_value.filter.return_value.distinct.return_value.all.return_value=[(17,)]
        devices=[
            {"device_id":17,"identity":"gone","subscription_id":42},
            {"device_id":18,"identity":"not-connected","subscription_id":43},
        ]
        with patch.object(collector,"_mark_presence",return_value={"closed":1}) as presence, \
             patch.object(collector,"_baseline_or_apply_cumulative") as meter:
            result=collector._apply_trusttunnel(
                db,node=SimpleNamespace(id=31),devices=devices,
                epoch="valid-epoch",rows=[])
        self.assertEqual(result["closed"],1)
        self.assertEqual(result["usage_events"],0)
        self.assertEqual(presence.call_count,1)
        self.assertEqual(presence.call_args.kwargs["device"]["device_id"],17)
        self.assertFalse(presence.call_args.kwargs["online"])
        meter.assert_not_called()


if __name__=="__main__":
    main()
