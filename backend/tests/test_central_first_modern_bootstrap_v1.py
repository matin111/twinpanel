"""First-install modern Exit profiles must originate in central catalog.

No customer identity, remote node settings or legacy Exit credentials may be
copied when a fresh hidden Exit is installed. The installer uses this plan
before central per-subscription runtime ownership takes over.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models import NodeType
from app.services.new_node_modern_bootstrap_v1 import build_modern_bootstrap_plan
from app.modern_protocol_runtime_v2 import SINGBOX_PROTOCOLS
from app.protocol_catalog import PROTOCOL_CATALOG


def fake_db(existing=None):
    db=MagicMock()
    target=SimpleNamespace(id=15,node_type=NodeType.EXIT,retired_at=None)
    # The first query is for Node; second is for target NodeProtocolConfig.
    db.query.return_value.filter.return_value.first.return_value=target
    db.query.return_value.filter.return_value.all.return_value=existing or []
    return db


class CentralFirstModernBootstrapTests(unittest.TestCase):
    def test_no_legacy_node_template_required_for_all_modern_protocols(self):
        db=fake_db()
        plan=build_modern_bootstrap_plan(db,15)
        self.assertEqual(set(plan["protocols"]),set(SINGBOX_PROTOCOLS))
        self.assertEqual(plan["skipped_no_template"],[])
        for protocol in plan["protocols"]:
            self.assertEqual(plan["ports"][protocol],
                             PROTOCOL_CATALOG[protocol]["default_port"])
            self.assertEqual(plan["profiles"][protocol],
                             {"preset":"recommended","settings":{}})
            self.assertEqual(plan["sources"][protocol]["mode"],
                             "central_catalog")
        # No source-node lookup: query() calls only target + target config.
        self.assertEqual(db.query.call_count,2)

    def test_conflicting_local_port_is_not_overwritten(self):
        db=fake_db([SimpleNamespace(
            protocol="existing",port=10808,status="online")])
        plan=build_modern_bootstrap_plan(db,15)
        self.assertNotIn("socks5",plan["protocols"])
        self.assertTrue(any(x["protocol"]=="socks5"
                            for x in plan["skipped_port_conflict"]))

    def test_installed_modern_listener_not_reinstalled(self):
        db=fake_db([SimpleNamespace(
            protocol="anytls",port=8446,status="online")])
        plan=build_modern_bootstrap_plan(db,15)
        self.assertIn("anytls",plan["already_online"])
        self.assertNotIn("anytls",plan["protocols"])


if __name__=="__main__":
    unittest.main()
