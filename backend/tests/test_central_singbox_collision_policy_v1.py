"""Central sing-box bulk: duplicate mother logins cannot stall the entire node."""
import json
import os
import tempfile
import unittest
from pathlib import Path

tmp=tempfile.TemporaryDirectory(prefix="tp-central-login-collisions-")
os.environ.setdefault("APP_SECRET_KEY","ci-central-identity-only")
os.environ.setdefault("DATABASE_URL",f"sqlite+pysqlite:///{Path(tmp.name)/'db.sqlite'}")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET","ci-central-identity-agent")

from app.central_singbox_collision_policy_v1 import resolve_node_login_collisions
from app.singbox_subscription_accounts import SingBoxAccountSecret
from app.central_singbox_bulk_runtime_v1 import remote_script

ROOT=Path(__file__).resolve().parents[1]


def secret(protocol,sid,username):
    return (sid,protocol,SingBoxAccountSecret(
        protocol=protocol,username=username,password=f"unchanged-password-{sid}",
    ))


class CentralSingboxCollisionTests(unittest.TestCase):
    def test_duplicate_mother_names_are_distinct_on_new_node(self):
        work=[secret("naive",19,"same"),secret("naive",23,"same"),
              secret("shadowtls",19,"same"),secret("shadowtls",23,"same"),
              secret("hysteria2",19,"tp-sub-19")]
        snapshot=[(sid,p,s.username,s.password) for sid,p,s in work]
        names=[(19,"naive","same"),(23,"naive","same"),
               (19,"shadowtls","same"),(23,"shadowtls","same")]
        out,changed=resolve_node_login_collisions(work,names)
        self.assertEqual(changed,4)
        self.assertEqual(len(out),len(work))
        self.assertEqual(len({(p,s.username) for _,p,s in out}),len(out))
        self.assertEqual([s.password for _,_,s in out],
                         [s.password for _,_,s in work])
        self.assertEqual([(sid,p,s.username,s.password) for sid,p,s in work],snapshot)
        self.assertEqual(out[-1][2].username,"tp-sub-19")
        self.assertEqual(out[0][2].username,"tp-central-19-naive")

    def test_identity_stability_across_retries_and_expiry(self):
        rows=[(19,"naive","common"),(23,"naive","common")]
        first,_=resolve_node_login_collisions([secret("naive",19,"common"),
                                                secret("naive",23,"common")],rows)
        second,_=resolve_node_login_collisions([secret("naive",23,"common")],rows)
        self.assertEqual(first[1][2].username,second[0][2].username)

    def test_unique_names_preserve_existing_login_without_alias(self):
        one=[secret("naive",19,"original-login"),
             secret("shadowtls",19,"original-login")]
        result,changed=resolve_node_login_collisions(one,[(19,"naive","original-login")])
        self.assertEqual(changed,0)
        self.assertEqual([x[2].username for x in result],
                         ["original-login","original-login"])

    def test_alias_namespace_collision_has_deterministic_fallback(self):
        rows=[(19,"naive","same"),(23,"naive","same"),
              (900,"naive","tp-central-23-naive")]
        result,changed=resolve_node_login_collisions([secret("naive",23,"same")],rows)
        self.assertEqual(changed,1)
        self.assertTrue(result[0][2].username.startswith("tp-central-23-"))
        self.assertNotEqual(result[0][2].username,"tp-central-23-naive")

    def test_non_bound_duplicate_fails_closed_instead_of_overwriting(self):
        with self.assertRaisesRegex(RuntimeError,"DUPLICATE_NODE_IDENTITY"):
            resolve_node_login_collisions([secret("anytls",19,"reused"),
                                           secret("anytls",23,"reused")],[])

    def test_remote_server_guard_prevents_replacing_other_customer(self):
        script=remote_script()
        compile(script,"<central-singbox-remote>","exec")
        self.assertIn("CENTRAL_SINGBOX_EXISTING_IDENTITY_MISMATCH",script)
        self.assertIn("old_record != new_record",script)
        self.assertEqual(script.count('["systemctl","restart",SERVICE+".service"]'),2)
        self.assertIn("SINGBOX_BATCH_CONFIG_INVALID",script)

if __name__=="__main__":
    unittest.main()
