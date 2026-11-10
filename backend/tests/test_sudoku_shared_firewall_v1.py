"""Ensure new/unchanged shared Sudoku Exits expose TCP 18553 without restarts."""
import ast
from pathlib import Path
import re
import unittest
from types import SimpleNamespace

SOURCE=(Path(__file__).resolve().parents[1]/"app/central_sudoku_shared_runtime_v2.py").read_text()
outer=ast.parse(SOURCE)
remote=next(n for n in outer.body if isinstance(n,ast.FunctionDef) and n.name=="remote_source")
remote_text=next(n.value.value for n in remote.body if isinstance(n,ast.Return))
tree=ast.parse(remote_text)
helper=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="ensure_public_shared_sudoku_port")

class FakeSubprocess:
    def __init__(self, mode): self.mode=mode;self.calls=[];self.added=False
    def run(self, cmd, **kwargs):
        self.calls.append(cmd)
        if cmd==["ufw","status"]:
            if self.mode=="missing":raise FileNotFoundError("ufw")
            if self.mode=="inactive":return SimpleNamespace(returncode=0,stdout="Status: inactive\n")
            if self.mode=="broken":return SimpleNamespace(returncode=1,stdout="")
            if self.mode=="already" or self.added:
                return SimpleNamespace(returncode=0,stdout="Status: active\n18553/tcp     ALLOW     Anywhere\n")
            return SimpleNamespace(returncode=0,stdout="Status: active\n22/tcp     ALLOW     Anywhere\n")
        if cmd[:2]==["ufw","allow"]:
            if self.mode=="deny":return SimpleNamespace(returncode=1,stdout="")
            self.added=True
            return SimpleNamespace(returncode=0,stdout="")
        raise AssertionError(f"Unexpected command: {cmd}")

class SharedSudokuFirewall(unittest.TestCase):
    def run_case(self, mode):
        fake=FakeSubprocess(mode)
        namespace={"subprocess":fake,"re":re,"PORT":18553}
        exec(compile(ast.Module(body=[helper],type_ignores=[]),"<remote>", "exec"),namespace)
        if mode in ("broken","deny"):
            with self.assertRaises(RuntimeError):
                namespace["ensure_public_shared_sudoku_port"]()
        else:
            namespace["ensure_public_shared_sudoku_port"]()
        self.assertTrue(all(cmd[:2] not in (["systemctl","restart"],["ufw","reset"]) for cmd in fake.calls))
        return fake

    def test_no_changes_inactive_missing_or_previously_allowed(self):
        for m in ("inactive","missing","already"):
            with self.subTest(m=m):
                fake=self.run_case(m)
                self.assertFalse(any(x[:2]==["ufw","allow"] for x in fake.calls))

    def test_add_only_18553_tcp_and_verify(self):
        fake=self.run_case("unallowed")
        commands=[x for x in fake.calls if x[:2]==["ufw","allow"]]
        self.assertEqual(commands,[["ufw","allow","18553/tcp","comment","TwinPanel Sudoku shared service"]])
        self.assertEqual(sum(1 for c in fake.calls if c==["ufw","status"]),2)

    def test_fail_closed_on_invalid_firewall(self):
        self.run_case("broken")
        self.run_case("deny")

    def test_both_apply_paths_protect_listener(self):
        self.assertIn('if previous==new and subprocess.run(',remote_text)
        idx=remote_text.index('if previous==new and subprocess.run(')
        fast=remote_text[idx:remote_text.index('sys.exit(0)',idx)]
        self.assertIn("ensure_public_shared_sudoku_port()",fast)
        idx=remote_text.index('if not verified:\n            raise RuntimeError("SUDOKU_SHARED_RUNTIME_USER_COUNT_MISMATCH")')
        self.assertIn("ensure_public_shared_sudoku_port()",remote_text[idx:idx+300])
        self.assertNotIn("systemctl restart",ast.get_source_segment(remote_text,helper) or "")

if __name__=="__main__":
    unittest.main()
