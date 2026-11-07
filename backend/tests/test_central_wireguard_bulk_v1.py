"""WireGuard central staging tests: one live sync, safe rollback and IP pool."""
from __future__ import annotations

import base64
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_test_bootstrap=tempfile.TemporaryDirectory(prefix="tp-central-wg-test-")
os.environ.setdefault("APP_SECRET_KEY","ci-only-central-wg")
os.environ.setdefault("DATABASE_URL",f"sqlite+pysqlite:///{Path(_test_bootstrap.name)/'bootstrap.db'}")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET","ci-only-wg-agent")

from app.central_wireguard_bulk_runtime_v1 import new_keypair,remote_script


class CentralWireguardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="wg-central-test-")
        self.root=Path(self.tmp.name)
        self.conf=self.root/"wg-access0.conf"
        self.state=self.root/"live-peers"
        self.counter=self.root/"syncs"
        self.interface_key=base64.b64encode(bytes(range(32))).decode()
        self.manual_pub=base64.b64encode(bytes(range(32,64))).decode()
        self.conf.write_text(
            "[Interface]\n"
            "PrivateKey = "+self.interface_key+"\n"
            "Address = 10.93.0.1/24, 10.96.0.1/21\n"
            "ListenPort = 51820\n"
            "\n[Peer]\n"
            "PublicKey = "+self.manual_pub+"\n"
            "AllowedIPs = 10.93.0.10/32\n",
            encoding="utf-8",
        )
        self.state.write_text(self.manual_pub+"\n",encoding="utf-8")
        self.tool=self.root/"wg"
        self.tool.write_text(
            "#!/usr/bin/env python3\n"
            "import os,sys,re,pathlib\n"
            "state=pathlib.Path(os.environ['WG_TEST_STATE'])\n"
            "args=sys.argv[1:]\n"
            "if args[:2]==['show','wg-access0'] and args[-1]=='peers':\n"
            " print(state.read_text(),end='');sys.exit(0)\n"
            "if args[:2]==['syncconf','wg-access0']:\n"
            " with open(os.environ['WG_TEST_COUNTER'],'a') as h:h.write('1\\n')\n"
            " flag=pathlib.Path(os.environ['WG_TEST_FAIL_FIRST'])\n"
            " if flag.exists():flag.unlink();sys.exit(5)\n"
            " doc=pathlib.Path(args[2]).read_text()\n"
            " keys=re.findall(r'(?m)^PublicKey\\s*=\\s*(\\S+)',doc)\n"
            " state.write_text('\\n'.join(keys)+'\\n')\n"
            " sys.exit(0)\n"
            "sys.exit(8)\n",
            encoding="utf-8",
        )
        self.tool.chmod(0o700)
        self.quick=self.root/"wg-quick"
        self.quick.write_text(
            "#!/bin/sh\nif [ \"$1\" = strip ]; then cat \"$2\";else exit 1;fi\n",
            encoding="utf-8",
        )
        self.quick.chmod(0o700)
        self.ip=self.root/"ip"
        self.ip.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = -4 ] && [ \"$2\" = -o ]; then echo '5: wg-access0 10.96.0.1/21'; exit 0; fi\n"
            "if [ \"$1\" = -4 ] && [ \"$2\" = route ]; then echo 'default via 172.31.1.1 dev eth0'; exit 0; fi\n"
            "exit 8\n",
            encoding="utf-8",
        )
        self.ip.chmod(0o700)
        self.iptables=self.root/"iptables"
        self.iptables.write_text(
            "#!/bin/sh\nif [ -e \""+str(self.root/"no-nat")+"\" ]; then exit 1; fi\nexit 0\n",
            encoding="utf-8",
        )
        self.iptables.chmod(0o700)

    def tearDown(self):
        self.tmp.cleanup()

    def stage(self,peers):
        src=remote_script(
            config_path=str(self.conf),interface="wg-access0",
            lock_path=str(self.root/"lock"),
        )
        compile(src,"<central-wg-remote>","exec")
        env={
            **os.environ,"PATH":str(self.root)+os.pathsep+os.environ["PATH"],
            "WG_TEST_STATE":str(self.state),
            "WG_TEST_COUNTER":str(self.counter),
            "WG_TEST_FAIL_FIRST":str(self.root/"fail-first"),
        }
        return subprocess.run([sys.executable,"-c",src],
            input=json.dumps({"peers":peers}),text=True,capture_output=True,
            timeout=35,env=env,
        )

    def test_keypairs_are_valid_curve25519(self):
        private,public=new_keypair()
        self.assertEqual(len(base64.b64decode(private,validate=True)),32)
        self.assertEqual(len(base64.b64decode(public,validate=True)),32)
        self.assertNotEqual(private,public)

    def test_batch_preserves_manual_peer_and_syncs_once(self):
        first,second=new_keypair(),new_keypair()
        rows=[{"id":4,"public":first[1]},{"id":5,"public":second[1]}]
        result=self.stage(rows)
        self.assertEqual(result.returncode,0,result.stderr[:280])
        x=json.loads(result.stdout)
        self.assertEqual(x["applied"],2)
        self.assertEqual(x["addresses"],{"4":"10.93.0.2","5":"10.93.0.3"})
        doc=self.conf.read_text()
        self.assertIn(self.manual_pub,doc)
        self.assertIn("TwinPanel-central subscription=4",doc)
        self.assertIn(first[1],doc)
        self.assertEqual(len(self.counter.read_text().splitlines()),1)
        self.assertEqual(stat.S_IMODE(self.conf.stat().st_mode),0o600)

    def test_same_public_key_and_address_are_idempotent(self):
        public=new_keypair()[1]
        row=[{"id":7,"public":public}]
        self.assertEqual(self.stage(row).returncode,0)
        second=self.stage(row)
        self.assertEqual(second.returncode,0,second.stderr[:300])
        self.assertFalse(json.loads(second.stdout)["changed"])
        self.assertEqual(len(self.counter.read_text().splitlines()),1)

    def test_nat_preflight_fails_without_modification(self):
        (self.root/"no-nat").touch()
        original=self.conf.read_bytes()
        result=self.stage([{"id":7,"public":new_keypair()[1]}])
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.conf.read_bytes(),original)

    def test_failed_live_sync_rolls_back_config_and_peers(self):
        (self.root/"fail-first").touch()
        original=self.conf.read_bytes()
        result=self.stage([{"id":7,"public":new_keypair()[1]}])
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.conf.read_bytes(),original)
        self.assertEqual(self.state.read_text(),self.manual_pub+"\n")

    def test_duplicate_and_invalid_keys_block_before_file_modification(self):
        original=self.conf.read_bytes()
        public=new_keypair()[1]
        for rows in [
            [{"id":1,"public":public},{"id":1,"public":public}],
            [{"id":1,"public":public},{"id":2,"public":public}],
            [{"id":3,"public":"not_a_public_key"}],
        ]:
            result=self.stage(rows)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(self.conf.read_bytes(),original)


if __name__=="__main__":
    unittest.main()
