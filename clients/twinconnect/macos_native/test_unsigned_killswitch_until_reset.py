"""An owned current-boot firewall has no automatic unlock deadline."""
import unittest
from unittest.mock import MagicMock, patch
import unsigned_killswitch_console_control as c

class UntilResetTests(unittest.TestCase):
    def setUp(self):
        self.lease={"phase":"owned","mode":c.SESSION_MODE,"nonce":"a"*32,
                    "created_at":1,"locked":False}
    def test_watchdog_never_releases_owned_firewall_after_time(self):
        with patch.object(c,"lock",return_value=MagicMock()), patch.object(c,"read_json",return_value=self.lease), patch.object(c,"monitor_lease",return_value="active"), patch.object(c,"restore_locked") as restore, patch.object(c,"publish") as publish, patch.object(c.time,"time",return_value=86400):
            self.assertTrue(c.watchdog_tick(self.lease["nonce"]))
            restore.assert_not_called()
            publish.assert_called_once_with("active","KS_WG_ACTIVE")
    def test_watchdog_restart_closes_instead_of_unlocking(self):
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=self.lease),patch.object(c,"close_lease") as close,patch.object(c,"restore_locked") as restore,patch.object(c,"publish"):
            self.assertTrue(c.watchdog_tick(self.lease["nonce"],restarted=True))
            close.assert_called_once_with(self.lease)
            restore.assert_not_called()
    def test_partial_owned_state_needs_manual_review(self):
        self.lease["phase"]="enabling"
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=self.lease),patch.object(c,"restore_locked") as restore,patch.object(c,"publish") as publish:
            self.assertTrue(c.watchdog_tick(self.lease["nonce"]))
            publish.assert_called_once_with("fault","KS_RECOVERY_REQUIRED")
            restore.assert_not_called()
    def test_manual_reset_ends_monitor(self):
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=None),patch.object(c,"restore_locked") as restore:
            self.assertFalse(c.watchdog_tick(self.lease["nonce"]))
            restore.assert_not_called()
    def test_until_reset_requires_matching_live_job(self):
        receipt={"nonce":self.lease["nonce"],"deadline":0,"mode":c.SESSION_MODE}
        with patch.object(c,"read_json",return_value=receipt),patch.object(c,"checked",return_value="state = running\n"+self.lease["nonce"]):
            self.assertEqual(c.session_deadline(self.lease),0)
        with patch.object(c,"read_json",return_value=receipt),patch.object(c,"checked",return_value="state = stopped"):
            with self.assertRaisesRegex(RuntimeError,"KS_RECOVERY_NOT_RUNNING"):
                c.session_deadline(self.lease)
    def test_prior_timed_lease_cannot_authorize_indefinite_mode(self):
        with patch.object(c,"read_json",return_value={"nonce":self.lease["nonce"],"deadline":1000}),patch.object(c,"checked") as run:
            with self.assertRaisesRegex(RuntimeError,"KS_SESSION_NOT_AUTHORIZED"):
                c.session_deadline(self.lease)
            run.assert_not_called()

if __name__=="__main__": unittest.main()
