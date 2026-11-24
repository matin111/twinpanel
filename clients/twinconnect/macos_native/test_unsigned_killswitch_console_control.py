"""Test the bounded UI helper without performing any PF mutations."""
import pathlib
import tempfile
import unittest
from unittest.mock import patch, Mock
import unsigned_killswitch_console_control as c

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.lease={"phase":"owned","nonce":"a"*32,"token":"123",
                    "canonical":["pass quick on lo0 all no state",
                                 "pass quick on utun15 all no state","block drop quick all"],
                    "pid":123,"interface":"utun15","locked":False,"reconnect_identity":{"protocol":"wireguard","ip":"1.2.3.4","port":51820,"uplink":"en0"}}
    def test_valid_worker_keeps_policy(self):
        with patch.object(c,"pf_enabled",return_value=True), patch.object(c,"anchor_rules",return_value=tuple(self.lease["canonical"])), patch.object(c,"process_command",return_value=c.WG_BIN+" -f utun15"), patch.object(c,"route_interface",side_effect=lambda ip: "en0" if ip=="1.2.3.4" else "utun15"), patch.object(c,"wg_uapi",return_value=c.Transport("1.2.3.4",51820,"udp")), patch.object(c,"checked") as checked:
            self.assertEqual(c.monitor_lease(self.lease),"active")
            checked.assert_not_called()
    def test_loss_closes_and_never_reopens(self):
        live=list(self.lease["canonical"])
        def command(*args,input=None,**kwargs):
            if "-n" in args: return input
            if "-f" in args: live[:]=c.lines(input)
            return ""
        with patch.object(c,"pf_enabled",return_value=True), patch.object(c,"anchor_rules",side_effect=lambda:tuple(live)), patch.object(c,"process_command",side_effect=ValueError("lost")), patch.object(c,"checked",side_effect=command) as checked, patch.object(c,"write_json"), patch.object(c,"session_deadline",return_value=999),patch.object(c,"publish"):
            self.assertEqual(c.monitor_lease(self.lease),"locked")
            self.assertTrue(self.lease["locked"])
            self.assertIn(c.PF,checked.call_args_list[1].args)
            self.assertEqual(tuple(live),c.lines(c.RULES))
            self.assertEqual(c.monitor_lease(self.lease),"locked")
            self.assertEqual(checked.call_count,2)
    def test_drift_and_disabled_are_not_active(self):
        with patch.object(c,"pf_enabled",return_value=False):
            with self.assertRaises(RuntimeError): c.monitor_lease(self.lease)
        with patch.object(c,"pf_enabled",return_value=True),patch.object(c,"anchor_rules",return_value=("pass all",)):
            with self.assertRaises(RuntimeError): c.monitor_lease(self.lease)
    def test_unowned_anchor_never_removed(self):
        with patch.object(c,"read_json",return_value=None),patch.object(c,"anchor_rules",return_value=("pass all",)),patch.object(c,"checked") as checked:
            with self.assertRaisesRegex(RuntimeError,"UNOWNED_ANCHOR_REFUSED"): c.restore_locked()
            checked.assert_not_called()
    def test_reset_owned_only(self):
        with tempfile.TemporaryDirectory() as d, patch.object(c,"STATE",pathlib.Path(d)),patch.object(c,"read_json",return_value=self.lease),patch.object(c,"anchor_rules",side_effect=[tuple(self.lease["canonical"]),()]),patch.object(c,"pf_enabled",side_effect=[True,False]),patch.object(c,"checked") as checked:
            self.assertTrue(c.restore_locked())
            self.assertEqual([x.args for x in checked.call_args_list],[(c.PF,"-a",c.ANCHOR,"-F","rules"),(c.PF,"-X","123")])
    def test_public_status_excludes_endpoint_and_token(self):
        with tempfile.TemporaryDirectory() as d,patch.object(c,"ROOT",pathlib.Path(d)):
            c.publish("locked","KS_TUNNEL_LOST_LOCKED",100)
            text=(pathlib.Path(d)/"status.json").read_text()
            self.assertIn('"persistent":false',text)
            self.assertIn('"session_limit":0',text)
            self.assertIn('"mode":"until_reset"',text)
            self.assertNotIn("token",text)
            self.assertNotIn("endpoint",text)
    def test_settings_control_uses_admin_authorization(self):
        source=pathlib.Path(__file__).with_name("TwinConnectMacOSNativeDashboard.swift").read_text()
        self.assertIn('preferenceRow("Kill Switch",',source)
        self.assertNotIn("Kill Switch • WireGuard",source)
        self.assertNotIn('subtitle: "WireGuard and AmneziaWG"',source)
        self.assertNotIn('"Connect WireGuard or AmneziaWG"',source)
        self.assertIn('with administrator privileges',source)
        self.assertIn('nativeKillSwitchControlStatus()',source)
        self.assertIn('row["persistent"] as? Bool == false',source)
        self.assertIn('Reset Internet',source)

if __name__=="__main__": unittest.main()
