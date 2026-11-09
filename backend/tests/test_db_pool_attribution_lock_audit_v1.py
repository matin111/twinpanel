"""No-DB regression: PostgreSQL session labels and redacted lock audit."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

from scripts.audit_database_lock_pressure_v1 import (
    ACTIVITY_SQL, BLOCKERS_SQL, _safe_rows,
)
from app import database


class PoolAttributionTests(unittest.TestCase):
    def test_worker_http_labels_are_different_and_preserve_lock_timeout(self):
        if database.settings.database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
            self.assertEqual(database._WORKER_CONNECT_ARGS["application_name"], "twinpanel-worker")
            self.assertEqual(database._REQUEST_CONNECT_ARGS["application_name"], "twinpanel-http")
            self.assertEqual(database._WORKER_CONNECT_ARGS.get("options"),
                             database._DATABASE_CONNECT_ARGS.get("options"))
            self.assertEqual(database._REQUEST_CONNECT_ARGS.get("options"),
                             database._DATABASE_CONNECT_ARGS.get("options"))
        else:
            self.assertNotIn("application_name", database._REQUEST_CONNECT_ARGS)
            self.assertNotIn("application_name", database._WORKER_CONNECT_ARGS)
        self.assertIs(database.SessionLocal.kw["bind"], database.engine)
        self.assertIs(database.RequestSessionLocal.kw["bind"], database.request_engine)

    def test_audit_only_outputs_allowlisted_aggregates(self):
        rows = [{
            "application_group": "twinpanel-http",
            "state": "idle in transaction",
            "wait_type": "Client",
            "sessions": 2,
            "oldest_txn_seconds": 45,
            "query": "SELECT password FROM sensitive",
            "pid": 1234,
        }]
        safe = _safe_rows(rows, (
            "application_group", "state", "wait_type",
            "sessions", "oldest_txn_seconds",
        ))
        self.assertEqual(len(safe), 1)
        self.assertNotIn("query", safe[0])
        self.assertNotIn("pid", safe[0])
        self.assertEqual(safe[0]["oldest_txn_seconds"], 45)

    def test_uses_pg_blocking_pids_without_mutations(self):
        self.assertIn("pg_blocking_pids(waiter.pid)", BLOCKERS_SQL)
        self.assertIn("pg_stat_activity", ACTIVITY_SQL)
        self.assertIn("pg_stat_activity", BLOCKERS_SQL)
        combined = (ACTIVITY_SQL + BLOCKERS_SQL).upper()
        for unsafe in ("PG_TERMINATE_BACKEND", "PG_CANCEL_BACKEND", "DELETE FROM",
                       "UPDATE ", "INSERT INTO", "DROP TABLE", "ALTER TABLE"):
            self.assertNotIn(unsafe, combined)

    def test_read_only_transaction_is_enforced(self):
        source = (Path(__file__).resolve().parents[1] /
                  "scripts/audit_database_lock_pressure_v1.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertIn("SET TRANSACTION READ ONLY", source)
        self.assertNotIn("session.commit(", source)
        self.assertNotIn("engine.begin(", source)
        self.assertTrue(any(isinstance(n, ast.FunctionDef) and n.name == "collect" for n in ast.walk(tree)))


if __name__ == "__main__":
    unittest.main()
