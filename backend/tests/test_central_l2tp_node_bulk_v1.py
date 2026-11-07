"""Unprivileged coverage of central L2TP materialization; no network calls."""
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

_bootstrap = tempfile.TemporaryDirectory(prefix="tp-central-l2tp-test-")
os.environ.setdefault("APP_SECRET_KEY", "test-only-central-l2tp-key")
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{Path(_bootstrap.name) / 'app.db'}")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET", "test-only-central-l2tp-agent")

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "twinpanel_central_l2tp_node_bulk_v1.py"
spec = importlib.util.spec_from_file_location("test_central_l2tp_node_bulk_script", MODULE)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)


class FakeSubscription:
    def __init__(self, sid, username, password):
        self.id = sid
        self.account_username = username
        self.account_password_encrypted = password


class CentralL2TPTests(unittest.TestCase):
    def run_remote(self, target: Path, accounts):
        src = mod.remote_merge_source(str(target))
        compile(src, "<central-l2tp-remote>", "exec")
        return subprocess.run(
            [sys.executable, "-c", src],
            input=json.dumps({"accounts": accounts}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )

    def test_dry_run_is_default_and_apply_requires_node_match(self):
        args = mod.args_parser(["--node-id", "14"])
        self.assertFalse(args.apply)
        self.assertEqual(args.limit, 3000)
        with self.assertRaises(SystemExit):
            mod.args_parser(["--node-id", "14", "--apply"])
        with self.assertRaises(SystemExit):
            mod.args_parser(["--node-id", "14", "--apply", "--confirm-node-id", "13"])

    def test_selected_accounts_require_valid_unique_central_identity(self):
        rows = mod.account_rows([
            FakeSubscription(1, "msabt1", "password1"),
            FakeSubscription(2, "msabt2", "pass=2!"),
        ])
        self.assertEqual([x["id"] for x in rows], [1, 2])
        with self.assertRaises(RuntimeError):
            mod.account_rows([FakeSubscription(1, "", "pass")])
        with self.assertRaises(RuntimeError):
            mod.account_rows([FakeSubscription(1, "msabt1", "")])
        with self.assertRaises(RuntimeError):
            mod.account_rows([FakeSubscription(1, "user", "a\nb")])
        duplicate_rows = mod.account_rows([
            FakeSubscription(1, "same", "pass1"),
            FakeSubscription(2, "same", "pass2"),
        ])
        self.assertEqual(
            [item["username"] for item in duplicate_rows],
            ["same", "tp-sub-2"],
        )
        self.assertEqual(
            mod.account_rows([
                FakeSubscription(1, "same", "pass1"),
                FakeSubscription(2, "same", "pass2"),
            ]), duplicate_rows,
        )
        with self.assertRaisesRegex(RuntimeError,"DUPLICATE_CENTRAL_SUBSCRIPTION_ID"):
            mod.account_rows([
                FakeSubscription(1, "same", "pass1"),
                FakeSubscription(1, "same", "pass1"),
            ])

    def test_remote_merge_preserves_unrelated_users_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "chap-secrets"
            target.write_text(
                "# managed remotely by sysadmin\n"
                "manual-user * old-manual-pass *\n"
                "msabt1 * wrong-password *\n",
                encoding="utf-8",
            )
            os.chmod(target, 0o600)
            accounts = [
                {"id": 1, "username": "msabt1", "password": "actual-secret"},
                {"id": 2, "username": "msabt2", "password": "punctuation-*!"},
            ]
            run1 = self.run_remote(target, accounts)
            self.assertEqual(run1.returncode, 0, run1.stderr[:400])
            result1 = json.loads(run1.stdout)
            self.assertEqual(result1, {"ok": True, "accounts": 2, "changed": True})
            doc = target.read_text(encoding="utf-8")
            self.assertIn("manual-user * old-manual-pass *", doc)
            self.assertNotIn("wrong-password", doc)
            self.assertIn('"msabt1" * "actual-secret"', doc)
            self.assertIn('"msabt2" * "punctuation-*!"', doc)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            backup = list((Path(temp) / ".twinpanel-central-l2tp-backups").glob("pre-bulk-*.secrets"))
            self.assertEqual(len(backup), 1)
            self.assertEqual(stat.S_IMODE(backup[0].stat().st_mode), 0o600)

            run2 = self.run_remote(target, accounts)
            self.assertEqual(run2.returncode, 0, run2.stderr[:400])
            self.assertFalse(json.loads(run2.stdout)["changed"])
            self.assertEqual(len(list((Path(temp) / ".twinpanel-central-l2tp-backups").glob("pre-bulk-*"))), 1)
            self.assertNotIn("actual-secret", run2.stdout)
            self.assertNotIn("punctuation-*!", run1.stdout)

    def test_duplicate_and_newline_payload_refused_before_file_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "chap-secrets"
            target.write_text("manual * protected *\n", encoding="utf-8")
            bad = [
                {"id": 1, "username": "same", "password": "a"},
                {"id": 2, "username": "same", "password": "b"},
            ]
            p = self.run_remote(target, bad)
            self.assertNotEqual(p.returncode, 0)
            self.assertEqual(target.read_text(encoding="utf-8"), "manual * protected *\n")
            p2 = self.run_remote(target, [{"id": 3, "username": "x", "password": "p\nq"}])
            self.assertNotEqual(p2.returncode, 0)
            self.assertEqual(target.read_text(encoding="utf-8"), "manual * protected *\n")

    def test_symlink_target_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            real = Path(temp) / "real"
            real.write_text("manual * protected *\n", encoding="utf-8")
            link = Path(temp) / "chap-secrets"
            link.symlink_to(real)
            p = self.run_remote(link, [{"id": 1, "username": "test1", "password": "p1"}])
            self.assertNotEqual(p.returncode, 0)
            self.assertEqual(real.read_text(encoding="utf-8"), "manual * protected *\n")


if __name__ == "__main__":
    unittest.main()
