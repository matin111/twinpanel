"""Offline guarded TUN helper tests; never start an engine."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
spec = importlib.util.spec_from_file_location(
    "unsigned_tun_helper", DIR / "unsigned_tun_helper.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class TrustedTunHelperTests(unittest.TestCase):
    def test_remote_root_session_refused(self):
        with mock.patch.object(helper.platform, "system", return_value="Darwin"), \
             mock.patch.object(helper.os, "geteuid", return_value=0), \
             mock.patch.dict(helper.os.environ, {"SSH_CONNECTION": "remote"}, clear=True):
            with self.assertRaisesRegex(ValueError, "REMOTE_SESSION_REFUSED"):
                helper.verify_local_operator()

    def test_unprivileged_user_refused(self):
        with mock.patch.object(helper.platform, "system", return_value="Darwin"), \
             mock.patch.object(helper.os, "geteuid", return_value=501), \
             mock.patch.dict(helper.os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "LOCAL_MACOS_ROOT_REQUIRED"):
                helper.verify_local_operator()

    def test_noninteractive_session_refused(self):
        with mock.patch.object(helper.platform, "system", return_value="Darwin"), \
             mock.patch.object(helper.os, "geteuid", return_value=0), \
             mock.patch.dict(helper.os.environ, {}, clear=True), \
             mock.patch.object(helper.sys.stdin, "isatty", return_value=False):
            with self.assertRaisesRegex(ValueError, "INTERACTIVE_LOCAL_CONSOLE_REQUIRED"):
                helper.verify_local_operator()

    def test_zero_duration_does_not_start_engine(self):
        with mock.patch.object(helper, "verify_local_operator"), \
             mock.patch.object(helper, "preflight"), \
             mock.patch.object(helper.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(ValueError, "INVALID_MAX_RUNTIME"):
                helper.perform_run(Path("/fake/engine"), Path("/fake/profile"), 0)
            popen.assert_not_called()

    def test_preflight_denied_before_child_launch(self):
        with mock.patch.object(helper, "verify_local_operator"), \
             mock.patch.object(helper, "preflight",
                               side_effect=ValueError("UNTRUSTED_CONFIG")), \
             mock.patch.object(helper.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(ValueError, "UNTRUSTED_CONFIG"):
                helper.perform_run(Path("/fake/engine"), Path("/fake/profile"), 20)
            popen.assert_not_called()

    def test_child_terminated_on_timeout(self):
        fake = mock.Mock()
        fake.pid = 18000
        fake.poll.return_value = None
        with mock.patch.object(helper, "verify_local_operator"), \
             mock.patch.object(helper, "preflight"), \
             mock.patch.object(helper.subprocess, "run"), \
             mock.patch.object(helper.subprocess, "Popen", return_value=fake), \
             mock.patch.object(helper.os, "killpg") as kill, \
             mock.patch.object(helper.time, "monotonic",
                               side_effect=[100.0, 102.0]), \
             mock.patch.object(helper.time, "sleep"):
            self.assertEqual(helper.perform_run(
                Path("/fake/engine"), Path("/fake/profile"), 1), 0)
            kill.assert_called_once_with(fake.pid, helper.signal.SIGTERM)
            fake.wait.assert_called_once_with(timeout=8)


if __name__ == "__main__":
    unittest.main()
