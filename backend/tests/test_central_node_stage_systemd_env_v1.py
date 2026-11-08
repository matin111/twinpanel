"""Transient central-stage workers must inherit the canonical server env files.

An unconfigured systemd-run worker exits with Pydantic missing Settings fields,
even though the API itself has a correct EnvironmentFile. This left newly
published Exits visible but stopped their durable delta reconciliation.
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("APP_SECRET_KEY","ci-central-stage-launcher")
os.environ.setdefault("DATABASE_URL","sqlite+pysqlite:////tmp/central-stage-env-only.sqlite3")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET","ci-central-stage-agent")

from app.services import central_node_stage_launcher_v1 as launcher


class CentralStageSystemdEnvTests(unittest.TestCase):
    def test_stage_has_canonical_environment_files_without_secret_argv(self):
        database=MagicMock()
        database.get.return_value=SimpleNamespace(show_to_users=True)
        with (
            patch.object(launcher,"ensure_launchable"),
            patch.object(launcher,"is_central_node",return_value=True),
            patch.object(launcher.shutil,"which",return_value="/usr/bin/systemd-run"),
            patch.object(launcher,"STAGE",SimpleNamespace(is_file=lambda:True)),
            patch.object(launcher.subprocess,"run",return_value=SimpleNamespace(returncode=0)) as run,
        ):
            response=launcher.launch(database,19,initial_full=False)

        argv=run.call_args.args[0]
        self.assertIn("--property=EnvironmentFile=/etc/twinpanel/backend.env",argv)
        self.assertIn("--property=EnvironmentFile=-/etc/twinpanel/install.env",argv)
        self.assertIn("--delta-only",argv)
        self.assertIn("--node-id",argv)
        self.assertIn("19",argv)
        self.assertTrue(response["scheduled"])
        self.assertNotIn(os.environ["APP_SECRET_KEY"]," ".join(map(str,argv)))
        self.assertNotIn(os.environ["NODE_AGENT_SHARED_SECRET"]," ".join(map(str,argv)))


if __name__=="__main__":
    unittest.main()
