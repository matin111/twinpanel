"""A healthy direct Exit must never be blocked by optional IR/Exit tunnel setup."""
from __future__ import annotations
import inspect
import unittest

from app.routers import provision
from app.routers import publish_node_all_users_v1 as install
from scripts import twinpanel_hidden_node_install_finish_v1 as finisher


class DirectExitWithoutTunnelTests(unittest.TestCase):
    def test_tunnel_bootstrap_failure_is_diagnostic_not_fatal(self):
        src=inspect.getsource(provision.install_node)
        self.assertIn('fabric = await _install_tunnel_fabric_base(',src)
        self.assertIn('"service": "failed"',src)
        self.assertNotIn('failed.append(\n                    "tunnel_fabric"',src)

    def test_new_exit_materialization_does_not_wait_for_tunnel(self):
        src=inspect.getsource(install._install_node_in_background)
        stage_src=inspect.getsource(finisher.finish)
        self.assertNotIn('and fabric.get("ok") is not False',src)
        self.assertNotIn('and fabric.get("ok") is not False',stage_src)
        self.assertIn("launch_hidden_node_finisher(",src)
        self.assertIn("admit_verified_exit(",stage_src)
        self.assertIn("launch(db,node_id,initial_full=True)",stage_src)
        self.assertLess(stage_src.index("admission=admit_verified_exit("),
                        stage_src.index("scheduled=launch("))
        self.assertIn("verify_new_exit_readiness",stage_src)
        # A healthy direct-only Exit can pass even if optional tunnel fabric
        # setup is incomplete. Do not reintroduce a tunnel prerequisite.
        self.assertNotIn("fabric.get(",stage_src)


if __name__=="__main__":
    unittest.main()
