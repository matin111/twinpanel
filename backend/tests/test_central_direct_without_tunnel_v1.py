"""A healthy direct Exit must never be blocked by optional IR/Exit tunnel setup."""
from __future__ import annotations
import inspect
import unittest

from app.routers import provision
from app.routers import publish_node_all_users_v1 as install


class DirectExitWithoutTunnelTests(unittest.TestCase):
    def test_tunnel_bootstrap_failure_is_diagnostic_not_fatal(self):
        src=inspect.getsource(provision.install_node)
        self.assertIn('fabric = await _install_tunnel_fabric_base(',src)
        self.assertIn('"service": "failed"',src)
        self.assertNotIn('failed.append(\n                    "tunnel_fabric"',src)

    def test_new_exit_materialization_does_not_wait_for_tunnel(self):
        src=inspect.getsource(install._install_node_in_background)
        self.assertNotIn('and fabric.get("ok") is not False',src)
        self.assertIn("central_stage.run",src)
        self.assertIn("verify_new_exit_readiness",src)


if __name__=="__main__":
    unittest.main()
