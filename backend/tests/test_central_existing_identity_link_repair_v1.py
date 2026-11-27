"""Safe node-link metadata recovery tests, no SSH/DB or subscription writes."""
from __future__ import annotations

import ast
import hashlib
import hmac
import secrets
from pathlib import Path
from unittest import TestCase,main

SOURCE=Path(__file__).resolve().parents[1]/"scripts/twinpanel_existing_identity_link_repair_v1.py"
TREE=ast.parse(SOURCE.read_text())
SCRIPT=SOURCE.read_text()


def proof_function():
    function=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=="state_proof")
    namespace={"hmac":hmac,"hashlib":hashlib}
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=[ast.ImportFrom(module="__future__",names=[ast.alias(name="annotations")],level=0),function],
        type_ignores=[])),str(SOURCE),"exec"),namespace)
    return namespace["state_proof"]


class ExactLinkRepairSafetyTests(TestCase):
    def test_cryptographic_exact_match_not_user_name_only(self):
        fn=proof_function()
        salt=secrets.token_bytes(32)
        a=fn("real-existing-credential",salt)
        self.assertEqual(a,hmac.new(salt,b"real-existing-credential",hashlib.sha256).hexdigest())
        self.assertNotEqual(fn("different-secret",salt),a)
        self.assertNotEqual(fn("real-existing-credential",secrets.token_bytes(32)),a)

    def test_remote_script_cannot_change_vpn_state_or_credentials(self):
        self.assertIn("REMOTE_AUDIT=r'''",SCRIPT)
        remote=SCRIPT.split("REMOTE_AUDIT=r'''",1)[1].split("'''",1)[0]
        for prohibited in ("systemctl", "restart", "write_text", "os.replace",
                           "open(", "chmod(", "unlink(", "config.json"):
            self.assertNotIn(prohibited,remote)
        self.assertIn('hmac.compare_digest',remote)
        self.assertIn('["awg","show","tpawg0","public-key"]',remote)

    def test_database_applier_only_changes_encrypted_delivery_metadata(self):
        node=next(n for n in TREE.body if isinstance(n,ast.FunctionDef)
                  and n.name=="apply_exact_matches")
        source=ast.unparse(node)
        self.assertIn("cred.config_text_encrypted = ad._enc(items)",source)
        self.assertNotIn("cred.secret_encrypted =",source)
        self.assertNotIn("traffic_used_bytes =",source)
        self.assertNotIn("expires_at =",source)
        self.assertIn("MAX_PATCH",source)
        self.assertIn("EXACT_LINK_NODE_MEMBERSHIP_CHANGED",source)
        self.assertIn("config_text_encrypted",source)
        self.assertIn("exact-identity-links-20261127",source)

    def test_apply_requires_exact_node_and_stage_exclusion(self):
        self.assertIn('fcntl.LOCK_EX | fcntl.LOCK_NB',ast.unparse(TREE))
        self.assertIn('args.apply and args.confirm_node_id != args.node_id',SCRIPT)
        self.assertIn('"node_service_restart":False',SCRIPT)
        self.assertIn('"quota_or_expiry_modified":False',SCRIPT)


if __name__=="__main__":
    main()
