"""Regression tests for read-only, UUID-preserving legacy Xray repair."""
import ast
from pathlib import Path
import unittest

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "scripts/twinpanel_legacy_xray_metadata_repair_v1.py"
)


class LegacyXrayMetadataRepairTests(unittest.TestCase):
    def test_read_only_node_inventory(self):
        src=SOURCE.read_text(encoding="utf-8")
        ast.parse(src)
        remote=src.split('_REMOTE = r"""',1)[1].split('"""',1)[0]
        self.assertIn('conf.read_text',remote)
        self.assertIn('systemctl","is-active"',remote)
        for forbidden in ('systemctl restart','systemctl stop',
                          'os.replace','write_text','subprocess.run(["xray"'):
            self.assertNotIn(forbidden,remote)

    def test_existing_node_uuid_is_required(self):
        src=SOURCE.read_text(encoding="utf-8")
        self.assertIn('if existing_id and existing_id!=ident:',src)
        self.assertIn('uuid_from_item(own[0])!=ident',src)
        self.assertIn('if not entitlement_ok(db,sid,args.node_id):',src)
        self.assertIn('with_for_update().all()',src)
        self.assertIn('is_central_node(db, node_id)',src)

    def test_central_metadata_repair_requires_explicit_flag_and_live_identity(self):
        src=SOURCE.read_text(encoding="utf-8")
        self.assertIn('p.add_argument("--central-only"',src)
        self.assertIn('bool(is_central_node(db, node_id)) != bool(central_only)',src)
        self.assertIn('central_only=args.central_only',src)
        self.assertIn('if not ident:',src)
        self.assertIn('if existing_id and existing_id!=ident:',src)

    def test_public_ports_match_iran_ingress(self):
        src=SOURCE.read_text(encoding="utf-8")
        self.assertIn('xr.PROFILE_META[xr.PROFILE_XHTTP]["public_base"] = 24000',src)
        self.assertIn('xr.PROFILE_META[xr.PROFILE_WS]["public_base"] = 26000',src)
        self.assertIn('_activate_xray_install_runtime()',src)
        self.assertLess(src.index('_activate_xray_install_runtime()'),
                        src.index('with SessionLocal() as db:'))

    def test_stale_legacy_tls_public_ports_are_not_considered_complete(self):
        from scripts.twinpanel_legacy_xray_metadata_repair_v1 import (
            item_has_complete_profiles,
        )
        required=frozenset(("websocket_tls","xhttp_reality","tcp_tls"))
        def sample(ws, xhttp, tcp):
            return {"profiles":[
                {"id":"websocket_tls","uri":f"vless://UUID@v2fin.in88.sbs:{ws}?security=tls"},
                {"id":"xhttp_reality","uri":f"vless://UUID@v2fin.in88.sbs:{xhttp}?security=reality"},
                {"id":"tcp_tls","uri":f"vless://UUID@v2fin.in88.sbs:{tcp}?security=tls"},
            ]}
        self.assertTrue(item_has_complete_profiles(sample(26022,24022,28022),required,22))
        self.assertFalse(item_has_complete_profiles(sample(23322,23122,28022),required,22))
        self.assertFalse(item_has_complete_profiles(sample(26022,23122,28022),required,22))
        self.assertFalse(item_has_complete_profiles(sample(26022,24022,28019),required,22))
        self.assertFalse(item_has_complete_profiles(None,required,22))

    def test_domainless_legacy_completion_policy_is_preserved(self):
        from scripts.twinpanel_legacy_xray_metadata_repair_v1 import (
            item_has_complete_profiles,
        )
        item={"profiles":[
            {"id":"xhttp_reality","uri":"vless://UUID@host:23122?security=reality"},
            {"id":"tcp_reality","uri":"vless://UUID@host:38022?security=reality"},
            {"id":"tcp_reality_vision","uri":"vless://UUID@host:39022?security=reality"},
        ]}
        required=frozenset(("xhttp_reality","tcp_reality","tcp_reality_vision"))
        self.assertTrue(item_has_complete_profiles(item,required,22))

    def test_apply_is_opt_in_and_confirmed(self):
        src=SOURCE.read_text(encoding="utf-8")
        self.assertIn('if not args.apply:',src)
        self.assertIn('args.node_id!=args.confirm_node_id',src)
        self.assertIn('remote_files_changed":False',src)


if __name__ == "__main__":
    unittest.main()
