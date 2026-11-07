"""Non-production tests for central Cisco account staging, atomicity, identity."""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_test_bootstrap = tempfile.TemporaryDirectory(prefix="tp-cisco-central-test-")
os.environ.setdefault("APP_SECRET_KEY", "test-only-cisco-bulk-secret")
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+pysqlite:///{Path(_test_bootstrap.name) / 'bootstrap.db'}",
)
os.environ.setdefault("NODE_AGENT_SHARED_SECRET", "test-only-cisco-bulk-agent")

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location(
    "central_cisco_bulk_test_target",
    SCRIPT_DIR / "twinpanel_central_cisco_node_bulk_v1.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CentralCiscoTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory(prefix="cisco-sandbox-")
        self.root = Path(self.sandbox.name)
        self.tool = self.root / "ocpasswd"
        self.tool.write_text(
            "#!/usr/bin/env python3\n"
            "import pathlib,sys\n"
            "if len(sys.argv)<4 or sys.argv[1]!='-c': sys.exit(9)\n"
            "p=pathlib.Path(sys.argv[2]); name=sys.argv[3]\n"
            "lines=[x for x in p.read_text().splitlines() if x and not x.startswith(name+':')]\n"
            "pw=sys.stdin.readline().strip(); sys.stdin.readline()\n"
            "lines.append(name+':grp:fakehash_'+str(len(pw)))\n"
            "p.write_text('\\n'.join(lines)+'\\n')\n",
            encoding="utf-8",
        )
        self.tool.chmod(0o700)
        self.target = self.root / "auth"
        self.target.write_text("unrelated:grp:existing-hash\n", encoding="utf-8")

    def tearDown(self):
        self.sandbox.cleanup()

    def stage(self, accounts):
        program = mod.cisco_merge_script(str(self.target))
        compile(program, "<remote-cisco>", "exec")
        return subprocess.run(
            [sys.executable, "-c", program],
            input=json.dumps({"accounts": accounts}),
            capture_output=True,
            text=True,
            timeout=20,
            env={**os.environ, "PATH": str(self.root)+os.pathsep+os.environ["PATH"]},
        )

    def test_scoped_apply_confirmation(self):
        self.assertFalse(mod.parse_args(["--node-id", "14"]).apply)
        with self.assertRaises(SystemExit):
            mod.parse_args(["--node-id", "14", "--apply"])
        with self.assertRaises(SystemExit):
            mod.parse_args(["--node-id", "14", "--apply", "--confirm-node-id", "13"])

    def test_preserves_manual_accounts_and_updates_expected_users(self):
        result=self.stage([
            {"id":1,"username":"a","password":"abc123"},
            {"id":2,"username":"b","password":"XYZ0000"},
        ])
        self.assertEqual(result.returncode,0,result.stderr[:350])
        self.assertEqual(json.loads(result.stdout)["verified"],2)
        final=self.target.read_text(encoding="utf-8")
        self.assertIn("unrelated:grp:existing-hash",final)
        self.assertIn("a:grp:fakehash_6",final)
        self.assertIn("b:grp:fakehash_7",final)
        self.assertNotIn("abc123",result.stdout)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode),0o600)
        backups=list((self.root/".twinpanel-central-cisco-backups").glob("pre-bulk-*.auth"))
        self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_text(), "unrelated:grp:existing-hash\n")

    def test_invalid_duplicate_and_nul_identity_fail_without_mutating_target(self):
        initial=self.target.read_bytes()
        for bad in [
            [{"username":"same","password":"p1"},{"username":"same","password":"p2"}],
            [{"username":"x","password":"pw\nbroken"}],
            [{"username":"x","password":""}],
        ]:
            result=self.stage(bad)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(self.target.read_bytes(), initial)

    def test_failure_mid_batch_never_activates_partially_staged_file(self):
        tool=self.tool
        text=tool.read_text()
        tool.write_text(text.replace(
            "p=pathlib.Path(sys.argv[2]); name=sys.argv[3]",
            "p=pathlib.Path(sys.argv[2]); name=sys.argv[3]\n"
            "if name=='fail': sys.exit(8)",
        ),encoding="utf-8")
        result=self.stage([
            {"username":"a","password":"pw1"},
            {"username":"fail","password":"pw2"},
        ])
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.target.read_text(), "unrelated:grp:existing-hash\n")

    def test_refuses_auth_file_symlink(self):
        destination=self.root/"real-auth"
        destination.write_text("unrelated:grp:existing-hash\n", encoding="utf-8")
        self.target.unlink()
        self.target.symlink_to(destination)
        result=self.stage([{"username":"a","password":"pw1"}])
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(destination.read_text(), "unrelated:grp:existing-hash\n")


if __name__=="__main__":
    unittest.main()
