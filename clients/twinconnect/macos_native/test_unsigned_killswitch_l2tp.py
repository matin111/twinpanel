"""Offline L2TP ESP protection contracts. No firewall or route changes."""
import unittest
from unittest.mock import patch,MagicMock
import unsigned_killswitch_attestation as a
import unsigned_killswitch_console_control as c
import unsigned_killswitch_policy as p
import l2tp_management_route_guard as g

LOCAL="10.0.0.2"
PEER="1.2.3.4"
SAD=f"{LOCAL} {PEER}\n\tesp mode=transport\n\tstate=mature\n{PEER} {LOCAL}\n\tesp mode=transport\n\tstate=mature\n"
SPD=f"{LOCAL}[65151] {PEER}[1701] udp\n\tout ipsec\n\tesp/transport//require\n{PEER}[1701] {LOCAL}[65151] udp\n\tin ipsec\n\tesp/transport//require\n"

class L2TPProtectionTests(unittest.TestCase):
    def test_bidirectional_esp_and_required_policy(self):
        self.assertTrue(a.l2tp_esp_pair(SAD,SPD,LOCAL,PEER))
        self.assertFalse(a.l2tp_esp_pair(SAD,SPD,LOCAL,"8.8.8.8"))
        self.assertFalse(a.l2tp_esp_pair(SAD.replace("mature","dead"),SPD,LOCAL,PEER))
        self.assertFalse(a.l2tp_esp_pair(SAD,SPD.replace("require","use"),LOCAL,PEER))
        self.assertFalse(a.l2tp_esp_pair(SAD.replace(LOCAL+" "+PEER,LOCAL+"[4500] "+PEER+"[4500]"),SPD,LOCAL,PEER))
        self.assertFalse(a.l2tp_esp_pair(SAD,SPD.replace("1701","9999"),LOCAL,PEER))
    def test_esp_policy_restricts_peer_and_never_plaintext(self):
        rules=p.render_l2tp_policy("ppp0","en0",LOCAL,PEER)
        self.assertIn("pass quick on ppp0 all no state",rules)
        self.assertIn(f"proto esp from {LOCAL} to {PEER} no state",rules)
        self.assertIn(f"proto esp from {PEER} to {LOCAL} no state",rules)
        self.assertNotIn("1701",rules)
        self.assertNotIn("4500",rules)
        self.assertTrue(rules.endswith("block drop quick all\n"))
        self.assertNotIn("ppp",p.render_l2tp_policy(None,"en0",LOCAL,PEER))
        with self.assertRaises(ValueError): p.render_l2tp_policy("utun0","en0",LOCAL,PEER)
    def test_reconnect_attests_same_profile_and_outer_peer(self):
        identity={"protocol":"l2tp","digest":"a"*64,"ip":PEER,"port":500,"transport":"udp","uplink":"en0","local_ip":LOCAL}
        lease={"reconnect_identity":identity,"reconnect_stage":"handshake","reconnect_until":6000}
        evidence=a.Evidence("l2tp","ppp0","en0",(a.Transport(PEER,500,"udp"),),123,LOCAL)
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=lease),patch.object(c,"session_deadline",return_value=0),patch.object(c,"root_private_json",return_value={"profile_digest":"a"*64}),patch.object(c,"l2tp_evidence",return_value=evidence),patch.object(c,"l2tp_local_ip",return_value=LOCAL),patch.object(c.time,"time",return_value=5000),patch.object(c,"replace_owned_policy") as replace:
            with self.assertRaisesRegex(RuntimeError,"KS_RECONNECT_PEER_UNVERIFIED"): c.attach_l2tp_reconnect(123,"ppp0","b"*64)
            replace.assert_not_called()
            c.attach_l2tp_reconnect(123,"ppp0","a"*64)
            self.assertEqual(replace.call_args.kwargs["reconnect_stage"],"route")
    def test_disconnect_closes_first(self):
        lease={"reconnect_identity":{"protocol":"l2tp","digest":"a"*64},"locked":False,"pid":123,"interface":"ppp0"}
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=lease),patch.object(c,"close_lease") as close:
            with self.assertRaisesRegex(RuntimeError,"KS_DISCONNECT_LEASE_MISMATCH"): c.before_l2tp_disconnect(124,"ppp0","a"*64)
            close.assert_not_called()
            c.before_l2tp_disconnect(123,"ppp0","a"*64)
            close.assert_called_once_with(lease)
    def test_guard_does_not_remove_routes_if_lock_refused(self):
        control=MagicMock()
        control.before_l2tp_disconnect.side_effect=RuntimeError()
        with patch.object(g,"load",return_value={"worker_pid":123,"profile_digest":"a"*64,"full_interface":"ppp0","mode":"leased"}),patch.object(g.os.path,"lexists",return_value=True),patch.object(g,"kill_switch_control",return_value=control),patch.object(g,"run") as calls:
            self.assertEqual(g.rollback(),"L2TP_KS_CLOSE_BEFORE_ROLLBACK_FAILED")
            calls.assert_not_called()
if __name__=="__main__": unittest.main()
