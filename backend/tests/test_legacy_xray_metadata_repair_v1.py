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

    def test_apply_is_opt_in_and_confirmed(self):
        src=SOURCE.read_text(encoding="utf-8")
        self.assertIn('if not args.apply:',src)
        self.assertIn('args.node_id!=args.confirm_node_id',src)
        self.assertIn('remote_files_changed":False',src)


if __name__ == "__main__":
    unittest.main()
