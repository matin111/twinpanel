"""Unit tests for central sing-box staging: no live SSH or service restart."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_db_bootstrap=tempfile.TemporaryDirectory(prefix="tp-singbox-bootstrap-")
os.environ.setdefault("APP_SECRET_KEY","ci-only-central-singbox")
os.environ.setdefault("DATABASE_URL",f"sqlite+pysqlite:///{Path(_db_bootstrap.name) / 'bootstrap.db'}")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET","ci-only-singbox-node-agent")

from app.central_singbox_bulk_runtime_v1 import remote_script
from app.modern_protocol_runtime_v2 import TAGS, SHADOWTLS_INNER_TAG


class CentralSingboxBulkTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(prefix="tp-central-singbox-")
        self.root=Path(self.folder.name)
        self.config=self.root/"singbox.json"
        self.state=self.root/"state.json"
        self.counter=self.root/"restart-count"
        self.lock=self.root/"lockfile"
        self.binary=self.root/"validate"
        self.binary.write_text("#!/bin/sh\nif [ -e \""+str(self.root/"fail-check")+"\" ]; then exit 1; fi\nexit 0\n",encoding="utf-8")
        self.binary.chmod(0o700)
        self.systemctl=self.root/"systemctl"
        self.systemctl.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = restart ]; then echo 1 >> \""+str(self.counter)+"\"; fi\n"
            "if [ -e \""+str(self.root/"fail-restart")+"\" ]; then exit 1; fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        self.systemctl.chmod(0o700)
        self.config.write_text(
            json.dumps({
                "inbounds":[
                    {"type":"hysteria2","tag":TAGS["hysteria2"],
                     "users":[{"name":"manual-user","password":"legacy-secret"}]},
                    {"type":"socks","tag":TAGS["socks5"],
                     "users":[{"username":"manual-socks","password":"legacy"}]},
                    {"type":"shadowtls","tag":TAGS["shadowtls"],
                     "users":[{"name":"__twinpanel_revoked__","password":"random"}]},
                ]
            }),encoding="utf-8",
        )

    def tearDown(self):
        self.folder.cleanup()

    def stage(self,updates):
        source=remote_script(
            config_path=str(self.config),state_path=str(self.state),
            service_name="twinpanel-singbox-test",binary_path=str(self.binary),
            lock_path=str(self.lock),
        )
        compile(source,"<central-singbox-remote>","exec")
        return subprocess.run(
            [sys.executable,"-c",source],
            input=json.dumps({"updates":updates}),
            text=True,capture_output=True,timeout=30,
            env={**os.environ,"PATH":str(self.root)+os.pathsep+os.environ["PATH"]},
        )

    def updates(self):
        return [
            {"protocol":"hysteria2","username":"new-user",
             "record":{"name":"new-user","password":"p-1"}},
            {"protocol":"socks5","username":"socks-user",
             "record":{"username":"socks-user","password":"p-2"}},
            {"protocol":"shadowtls","username":"shadow-user",
             "record":{"name":"shadow-user","password":"p-3"}},
        ]

    def test_bulk_updates_several_protocols_with_one_restart(self):
        result=self.stage(self.updates())
        self.assertEqual(result.returncode,0,result.stderr[:280])
        self.assertEqual(json.loads(result.stdout)["accounts"],3)
        self.assertEqual(len(self.counter.read_text().splitlines()),1)
        doc=json.loads(self.config.read_text())
        inbound={i["tag"]:i for i in doc["inbounds"]}
        self.assertIn({"name":"manual-user","password":"legacy-secret"},
                      inbound[TAGS["hysteria2"]]["users"])
        self.assertIn({"username":"manual-socks","password":"legacy"},
                      inbound[TAGS["socks5"]]["users"])
        self.assertEqual(inbound[TAGS["shadowtls"]]["detour"],SHADOWTLS_INNER_TAG)
        self.assertIn(SHADOWTLS_INNER_TAG,inbound)
        self.assertFalse(any(u.get("name")=="__twinpanel_revoked__"
                             for u in inbound[TAGS["shadowtls"]]["users"]))
        self.assertNotIn("p-1",result.stdout)
        self.assertNotIn("p-2",result.stdout)

    def test_repeating_same_accounts_does_not_restart(self):
        self.assertEqual(self.stage(self.updates()).returncode,0)
        second=self.stage(self.updates())
        self.assertEqual(second.returncode,0,second.stderr[:300])
        self.assertFalse(json.loads(second.stdout)["changed"])
        self.assertEqual(len(self.counter.read_text().splitlines()),1)

    def test_invalid_config_does_not_replace_file_or_restart(self):
        original=self.config.read_bytes()
        (self.root/"fail-check").touch()
        result=self.stage(self.updates())
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.config.read_bytes(),original)
        self.assertFalse(self.counter.exists())

    def test_bad_identity_or_duplicate_is_rejected(self):
        original=self.config.read_bytes()
        duplicate=self.updates()+[self.updates()[0]]
        result=self.stage(duplicate)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.config.read_bytes(),original)
        broken=[{"protocol":"hysteria2","username":"u",
                 "record":{"name":"not-u","password":"p"}}]
        result=self.stage(broken)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.config.read_bytes(),original)

    def test_failed_restart_rolls_config_back(self):
        original=self.config.read_bytes()
        (self.root/"fail-restart").touch()
        result=self.stage(self.updates())
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.config.read_bytes(),original)

    def test_symlink_config_not_modified(self):
        original=self.config
        alt=self.root/"original.json"
        original.rename(alt)
        original.symlink_to(alt)
        before=alt.read_bytes()
        result=self.stage(self.updates())
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(alt.read_bytes(),before)


if __name__=="__main__":
    unittest.main()
