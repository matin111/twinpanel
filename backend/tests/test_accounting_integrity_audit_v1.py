"""Metering integrity labels must not fabricate per-user traffic."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import TestCase, main

SCRIPT=Path(__file__).resolve().parents[1]/"scripts/twinpanel_accounting_integrity_audit_v1.py"
spec=importlib.util.spec_from_file_location("twinpanel_metering_audit",SCRIPT)
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AccountingIntegrityAuditTests(TestCase):
    def test_report_enumerates_every_registered_protocol_and_never_guesses_bytes(self):
        result=audit.build_report({}, {}, {})
        self.assertEqual(result["protocol_count"],16)
        self.assertEqual(len({x["protocol"] for x in result["protocols"]}),16)
        for item in result["protocols"]:
            self.assertEqual(item["recent_accepted_bytes"],0)
            self.assertIn(item["reliability"],
                {"no_active_quota_devices","per_user_attribution_unavailable"})

    def test_zero_only_trusttunnel_events_are_not_declared_accurate(self):
        result=audit.build_report(
            {"trusttunnel":{"active_credentials":1300}},
            {"trusttunnel":{"event_count":190000,"positive_count":0,
                            "accepted_bytes":0,"billable_bytes":0}},
            {"trusttunnel":1200})
        row=next(x for x in result["protocols"] if x["protocol"]=="trusttunnel")
        self.assertEqual(row["reliability"],"only_zero_byte_events_verify_at_source")
        self.assertEqual(row["recent_accepted_bytes"],0)

    def test_positive_source_and_unattributable_source_are_distinct(self):
        result=audit.build_report({},
            {"openconnect":{"event_count":9,"positive_count":7,
                            "accepted_bytes":10000,"billable_bytes":10000}},
            {"cisco":3,"shadowtls":1})
        by={x["protocol"]:x for x in result["protocols"]}
        self.assertEqual(by["cisco"]["recent_accepted_bytes"],10000)
        self.assertEqual(by["cisco"]["reliability"],"positive_attributed_ledger_evidence")
        self.assertEqual(by["shadowtls"]["reliability"],"per_user_attribution_unavailable")

    def test_negative_counters_are_flagged_not_clamped(self):
        result=audit.build_report({},{"wireguard":{"event_count":4,"positive_count":2,
          "invalid_count":1,"accepted_bytes":100,"billable_bytes":100}},
          {"wireguard":1})
        row=next(x for x in result["protocols"] if x["protocol"]=="wireguard")
        self.assertEqual(row["reliability"],"invalid_counter_events_need_review")


if __name__=="__main__":
    main()
