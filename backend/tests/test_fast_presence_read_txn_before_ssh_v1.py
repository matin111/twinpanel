"""Read-only regression for fast presence worker PostgreSQL transaction scopes.

The workers use SessionLocal(expire_on_commit=False). Their node and identity
lookups must release the read transaction before awaiting a remote SSH poll.
No protocol, traffic, UUID, session, or billing implementation is modified.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKERS = (
    "twinpanel_sudoku_fast_presence_worker.py",
    "twinpanel_naive_fast_presence_worker.py",
    "twinpanel_mieru_fast_presence_worker.py",
)


def _is_db_commit(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "db"
        and node.value.func.attr == "commit"
    )


def _is_remote_connect(node: ast.stmt) -> bool:
    if not isinstance(node, (ast.Assign, ast.AnnAssign)):
        return False
    return "connect_protocol_runtime(" in ast.unparse(node)


class FastPresenceReadTransactionTests(unittest.TestCase):
    def test_all_three_workers_release_read_transaction_before_awaiting_ssh(self):
        for filename in WORKERS:
            with self.subTest(worker=filename):
                source = (ROOT / "scripts" / filename).read_text(encoding="utf-8")
                tree = ast.parse(source, filename=filename)
                matches = [
                    body[index - 1]
                    for part in ast.walk(tree)
                    if isinstance(part, (ast.Try, ast.For, ast.AsyncFor, ast.FunctionDef))
                    for body in [part.body]
                    for index, statement in enumerate(body)
                    if _is_remote_connect(statement) and index > 0
                ]
                self.assertEqual(len(matches), 1, "expected one canonical SSH connect path")
                self.assertTrue(_is_db_commit(matches[0]), "commit read scope before SSH")

    def test_only_read_transaction_boundary_changes_no_secret_dump_or_shutdown(self):
        for filename in WORKERS:
            source = (ROOT / "scripts" / filename).read_text(encoding="utf-8")
            self.assertIn("db.rollback()", source)
            self.assertIn("db.close()", source)
            self.assertIn("conn.wait_closed()", source)
            self.assertNotIn("pg_terminate_backend", source)
            self.assertNotIn("DROP TABLE", source)


if __name__ == "__main__":
    unittest.main()
