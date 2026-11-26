"""Offline behavioral tests for the real quota guard and pure evidence builder.

Uses AST isolation so CI never opens an app DB connection on import.
"""
from __future__ import annotations

import ast
from typing import Any
from pathlib import Path
from unittest import TestCase, main

ROOT = Path(__file__).resolve().parents[1] / "app"
SCRIPTS = ROOT.parent / "scripts"


def _module_constants(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            try:
                values[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError, KeyError):
                pass
    values["ALL_PROTOCOL_KEYS"] = values["CLASSIC_PROTOCOL_KEYS"] + values["MODERN_PROTOCOL_KEYS"]
    values["ALL_PROTOCOL_SET"] = frozenset(values["ALL_PROTOCOL_KEYS"])
    return values


def _load_functions(path: Path, names: set[str], namespace: dict) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    kept = [node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(kept) == len(names), (path, names)
    # Prevent incidental application model/database initialization.
    code = compile(ast.fix_missing_locations(ast.Module(body=kept,type_ignores=[])),str(path),"exec")
    exec(code,namespace)
    return namespace


registry = _module_constants(ROOT / "protocol_account_registry.py")
_load_functions(ROOT / "protocol_account_registry.py", {"canonical_protocol"}, registry)
guard = _load_functions(
    ROOT / "quota_source_identity_v1.py", {"device_protocol_is_source"},
    {"canonical_protocol": registry["canonical_protocol"]},
)
audit = _load_functions(
    SCRIPTS / "twinpanel_central_quota_evidence_v1.py",
    {"_canonical","_protocol_totals","build_report"},
    {"ALL_PROTOCOL_KEYS":registry["ALL_PROTOCOL_KEYS"],
     "canonical_protocol":registry["canonical_protocol"], "Any":Any},
)


class CentralQuotaContractTests(TestCase):
    def test_all_registered_protocols_match_own_device(self):
        self.assertEqual(len(registry["ALL_PROTOCOL_KEYS"]),16)
        check = guard["device_protocol_is_source"]
        for protocol in registry["ALL_PROTOCOL_KEYS"]:
            self.assertTrue(check(protocol,protocol),protocol)

    def test_known_aliases_are_not_double_billed_or_rejected(self):
        check = guard["device_protocol_is_source"]
        self.assertTrue(check("cisco","openconnect"))
        self.assertTrue(check("v2ray","xray"))
        self.assertTrue(check("naive","naiveproxy"))
        self.assertTrue(check("l2tp","l2tp/ipsec"))

    def test_cross_protocol_and_unknown_identity_rejected(self):
        check=guard["device_protocol_is_source"]
        for p in registry["ALL_PROTOCOL_KEYS"]:
            for q in registry["ALL_PROTOCOL_KEYS"]:
                self.assertEqual(check(p,q),p==q,(p,q))
        for p,q in [(None,"openvpn"),("openvpn",None),("wireguard",""),("shadowtls","shared"),("bogus","bogus")]:
            self.assertFalse(check(p,q))

    def test_evidence_distinguishes_metering_from_idle_counter(self):
        report=audit["build_report"](
            devices=[{"protocol":"shadowtls","device_count":100},
                     {"protocol":"wireguard","device_count":10},
                     {"protocol":"v2ray","device_count":1}],
            cursors=[{"protocol":"shadowtls","cursor_count":30,"recent_cursors":15},
                     {"protocol":"wireguard","cursor_count":10,"recent_cursors":10},
                     {"protocol":"xray","cursor_count":1,"recent_cursors":1}],
            positive_events=[{"protocol":"wireguard","positive_events":2,"accepted_bytes":1000},
                             {"protocol":"xray","positive_events":1,"accepted_bytes":200}],
            cursor_device_pairs=[{"source_protocol":"xray","device_protocol":"v2ray","cursor_count":1}],
            expiry_flags={"active_expiry_without_start":2},
            enforcement=[{"command_type":"revoke_subscription","status":"failed","count":3},
                         {"command_type":"revoke_subscription","status":"controller_pending","count":5}],
            observed_at_utc="2026-11-26T00:00:00Z",
        )
        by_protocol={v["protocol"]:v for v in report["protocols"]}
        self.assertEqual(report["registered_protocols"],16)
        self.assertEqual(by_protocol["shadowtls"]["evidence"],"unverified_shadowtls_identity_inner")
        self.assertEqual(by_protocol["shadowtls"]["accepted_bytes_6h"],0)
        self.assertEqual(by_protocol["wireguard"]["evidence"],"positive_attributed_ledger_events")
        self.assertEqual(by_protocol["v2ray"]["accepted_bytes_6h"],200)
        self.assertEqual(report["cursor_identity_mismatch_count"],0)
        self.assertEqual(report["revoke_commands_failed_24h"],3)
        self.assertEqual(report["revoke_commands_pending_24h"],5)
        self.assertEqual(report["first_use_date_flags"]["active_expiry_without_start"],2)

    def test_mismatched_cursor_is_visible_and_never_healthy(self):
        report=audit["build_report"](
            devices=[],cursors=[],
            positive_events=[{"protocol":"xray","positive_events":10,"accepted_bytes":100}],
            cursor_device_pairs=[{"source_protocol":"xray","device_protocol":"wireguard","cursor_count":4}],
            expiry_flags={},enforcement=[],observed_at_utc="now",
        )
        row=next(x for x in report["protocols"] if x["protocol"]=="v2ray")
        self.assertEqual(row["evidence"],"cursor_device_protocol_mismatch")
        self.assertEqual(report["cursor_identity_mismatch_count"],4)


if __name__=="__main__":
    main()
