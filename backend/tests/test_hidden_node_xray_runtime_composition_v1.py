"""Regression: detached node finisher must compose the same three Xray profiles as API.

Offline test: no SSH, network, database mutation or systemctl execution.
"""
import os
import unittest

os.environ.setdefault("APP_SECRET_KEY", "ci-hidden-xray-composition")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:////tmp/ci-hidden-xray-composition.sqlite3")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET", "ci-hidden-xray-composition-agent")

from app import xray_modern_runtime
from app.xray_domainless_vision_v50 import ensure_modern_xray_v50
from scripts import twinpanel_hidden_node_install_finish_v1 as worker


class DetachedXrayRuntimeCompositionTests(unittest.TestCase):
    def test_worker_activates_three_profile_composition(self):
        worker._activate_xray_install_runtime()
        self.assertIs(xray_modern_runtime._ensure_modern_xray, ensure_modern_xray_v50)

    def test_activation_is_idempotent(self):
        worker._activate_xray_install_runtime()
        first = xray_modern_runtime._ensure_modern_xray
        worker._activate_xray_install_runtime()
        self.assertIs(xray_modern_runtime._ensure_modern_xray, first)


if __name__ == "__main__":
    unittest.main()
