"""Cisco TCP-only shared protection contracts; no real network mutations."""
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
import unsigned_killswitch_console_control as c
import unsigned_killswitch_attestation as a
import cisco_management_route_guard as g

class CiscoProtectionTests(unittest.TestCase):
    def setUp(self):
        self.identity={"protocol":"cisco","digest":"a"*64,"ip":"1.2.3.4","port":443,
                       "transport":"tcp","uplink":"en0","gateway":"1.2.3.1",
                       "baseline_ip":"8.8.4.4"}
        self.lease={"phase":"owned","locked":True,"reconnect_stage":"handshake",
                    "reconnect_until":5060,"pid":123,"interface":"utun15",
                    "reconnect_identity":self.identity,"canonical":list(c.lines(c.RULES))}
    def test_attach_requires_matching_profile_and_live_exact_peer(self):
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=self.lease),patch.object(c,"session_deadline",return_value=0),patch.object(c.time,"time",return_value=5000),patch.object(c,"route_interface",return_value="en0"),patch.object(c,"cisco_tcp_transport",return_value=a.Transport("1.2.3.4",443,"tcp")) as peer,patch.object(c,"replace_owned_policy") as replace:
            with self.assertRaisesRegex(RuntimeError,"KS_RECONNECT_PEER_UNVERIFIED"):
                c.attach_cisco_reconnect(125,"utun16","b"*64)
            replace.assert_not_called()
            c.attach_cisco_reconnect(125,"utun16","a"*64)
            self.assertIn("pass quick on utun16 all no state",replace.call_args.args[1])
            self.assertIn("to 1.2.3.4 port = 443 user = root",replace.call_args.args[1])
            peer.return_value=a.Transport("1.2.3.4",444,"tcp")
            replace.reset_mock()
            with self.assertRaisesRegex(RuntimeError,"KS_RECONNECT_PEER_UNVERIFIED"):
                c.attach_cisco_reconnect(125,"utun16","a"*64)
            replace.assert_not_called()
    def test_disconnect_closes_before_route_removal(self):
        self.lease.update(locked=False,reconnect_stage=None)
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=self.lease),patch.object(c,"close_lease") as close:
            with self.assertRaisesRegex(RuntimeError,"KS_DISCONNECT_LEASE_MISMATCH"):
                c.before_cisco_disconnect(124,"utun15")
            close.assert_not_called()
            c.before_cisco_disconnect(123,"utun15")
            close.assert_called_once_with(self.lease)
        state={"mode":"leased","worker_pid":123,"full_interface":"utun15",
               "interface":"en0","gateway":"1.2.3.1","peers":[]}
        control=MagicMock()
        control.before_cisco_disconnect.side_effect=RuntimeError("unverified")
        with patch.object(g,"load",return_value=state),patch.object(g.os.path,"lexists",return_value=True),patch.object(g,"kill_switch_control",return_value=control),patch.object(g,"run") as run:
            self.assertEqual(g.rollback(),"CISCO_KS_CLOSE_BEFORE_ROLLBACK_FAILED")
            run.assert_not_called()
    def test_cisco_bootstrap_has_no_udp_dns_or_tunnel(self):
        rules=c.bootstrap_rules(self.identity)
        self.assertIn("proto tcp",rules)
        self.assertNotIn("proto udp",rules)
        self.assertNotIn("utun",rules)
        self.assertTrue(rules.endswith("block drop quick all\n"))
    def test_app_profile_is_account_and_location_bound(self):
        src=Path(__file__).with_name("TwinConnectMacOSNativeDashboard.swift").read_text()
        self.assertIn("ciscoReconnectAccount == session.namespace",src)
        self.assertIn("ciscoReconnectOrigin == session.apiOrigin",src)
        self.assertIn("ciscoReconnectServer == serverID",src)
        self.assertIn("ciscoReconnectProfile = nil",src)
        self.assertIn("complete(.success(cached))",src)
if __name__=="__main__": unittest.main()
