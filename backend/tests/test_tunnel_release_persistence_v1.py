"""Release-source regression guard for selected Tunnel bootstrap DB session lifetime.

Run: python backend/tests/test_tunnel_release_persistence_v1.py
This intentionally performs no network operations, DB mutations, or tunnel work.
"""
from __future__ import annotations

import ast
import pathlib
import unittest

APP = pathlib.Path(__file__).resolve().parents[1] / "app"


class TunnelReleasePersistenceTests(unittest.TestCase):
    def test_exit_agent_lookup_releases_db_before_remote_await(self) -> None:
        source = (APP / "node_bootstrap_control_v66.py").read_text()
        fn = next(node for node in ast.parse(source).body
                  if isinstance(node, ast.AsyncFunctionDef)
                  and node.name == "_install_or_upgrade_agent_v70")
        # The entire initial DB transaction closes before any await / SSH call.
        first_await = min(node.lineno for node in ast.walk(fn)
                          if isinstance(node, ast.Await))
        finalizers = [n for n in ast.walk(fn) if isinstance(n, ast.Try)
                      and any(isinstance(f, ast.Expr)
                              and isinstance(f.value, ast.Call)
                              and isinstance(f.value.func, ast.Attribute)
                              and f.value.func.attr == "close"
                              for f in n.finalbody)]
        self.assertTrue(finalizers, "Exit lookup must close DB in a finally clause")
        self.assertLess(min(n.lineno for n in finalizers), first_await)

    def test_tunnel_bootstrap_does_not_hold_read_transaction_across_ssh(self) -> None:
        source = (APP / "routers" / "tunnels.py").read_text()
        start = source.index("async def _ensure_fabric_for_tunnel_node(")
        body = source[start:source.index("# TWINPANEL_TUNNEL_BOOTSTRAP_COALESCE", start)]
        self.assertIn("db.commit()", body)
        self.assertIn("TUNNEL_BOOTSTRAP_UNEXPECTED_DB_WRITES", body)
        self.assertLess(body.index("db.commit()"), body.index("await _install_or_upgrade_agent("))

    def test_job_exposes_classified_db_error_without_secret(self) -> None:
        source = (APP / "routers" / "tunnel_selected_jobs_v1.py").read_text()
        self.assertIn("TUNNEL_CREATE_DB_CONNECTION_LOST", source)
        self.assertIn("TUNNEL_CREATE_NODE_BOOTSTRAP_FAILED", source)
        self.assertIn("error_code=:code", source)

    def test_iran_python_bootstrap_has_safe_fallback(self) -> None:
        source = (APP / "provision_resilience_v278.py").read_text()
        self.assertIn("ensurepip", source)
        self.assertIn("system_packages_direct", source)


if __name__ == "__main__":
    unittest.main()
