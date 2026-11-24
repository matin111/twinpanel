"""Offline tests for the OpenVPN shared protection adapter."""
import hashlib
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import openvpn_app_session as o
import unsigned_killswitch_console_control as c
import unsigned_killswitch_attestation as a
from test_openvpn_profile_review import SAFE

class OpenVPNProtectionTests(unittest.TestCase):
    def setUp(self):
        self.raw=SAFE.encode()
        self.identity={"protocol":"openvpn","digest":hashlib.sha256(self.raw).hexdigest(),
            "ip":"1.2.3.4","port":1194,"transport":"udp","uplink":"en0",
            "gateway":"1.2.3.1","baseline_ip":"8.8.4.4"}
        self.lease={"phase":"owned","nonce":"a"*32,"token":"123","locked":True,
                    "mode":"until_reset","canonical":list(c.lines(c.RULES)),
                    "pid":124,"route_worker":123,"interface":"utun15",
                    "reconnect_identity":self.identity}
    def test_same_profile_pin_keeps_certificate_checks(self):
        prepared=o.safe_config(self.raw,self.identity).decode()
        self.assertIn("remote 1.2.3.4 1194",prepared)
        self.assertIn("remote-cert-tls server",prepared)
        self.assertIn("proto udp4",prepared)
        self.assertNotIn("vpn.example.com",prepared)
        with self.assertRaisesRegex(ValueError,"OPENVPN_KS_TRANSPORT_CHANGED"):
            o.safe_config(self.raw,{**self.identity,"port":443})
    def test_multiple_remotes_cannot_be_pinned(self):
        with self.assertRaisesRegex(ValueError,"OPENVPN_KS_MULTIPLE_REMOTES"):
            o.safe_config(self.raw+b"\nremote vpn2.example.com 1194\n",self.identity)
    def test_peer_requires_completed_handshake(self):
        line=b"UDPv4 link remote: [AF_INET]1.2.3.4:1194\n"
        self.assertIsNone(o.authenticated_peer(line))
        self.assertEqual(o.authenticated_peer(line+o.SUCCESS),("1.2.3.4",1194,"udp"))
        self.assertEqual(o.authenticated_peer(b"TCP connection established with [AF_INET]1.2.3.4:443\n"+o.SUCCESS),("1.2.3.4",443,"tcp"))
    def test_tcp_bootstrap_exact_endpoint_and_no_direct_dns(self):
        rules=c.bootstrap_rules({**self.identity,"transport":"tcp","port":443})
        self.assertIn("proto tcp",rules)
        self.assertIn("to 1.2.3.4 port = 443 user = root",rules)
        self.assertNotIn("utun",rules)
        self.assertTrue(rules.endswith("block drop quick all\n"))
    def test_attach_checks_authenticated_child_and_digest(self):
        self.lease.update(reconnect_stage="handshake",reconnect_until=5060)
        evidence=a.Evidence("openvpn","utun16","en0",(a.Transport("1.2.3.4",1194,"udp"),),126)
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=self.lease),patch.object(c,"session_deadline",return_value=0),patch.object(c.time,"time",return_value=5000),patch.object(c,"openvpn_session_evidence",return_value=(evidence,125,self.identity["digest"])) as proof,patch.object(c,"replace_owned_policy") as replace:
            self.assertEqual(c.attach_openvpn_reconnect(125,"utun16"),126)
            self.assertIn("pass quick on utun16 all no state",replace.call_args.args[1])
            replace.reset_mock()
            proof.return_value=(evidence,125,"b"*64)
            with self.assertRaisesRegex(RuntimeError,"KS_RECONNECT_PEER_UNVERIFIED"):
                c.attach_openvpn_reconnect(125,"utun16")
            replace.assert_not_called()
    def test_close_before_own_route_worker_disconnect(self):
        self.lease["locked"]=False
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=self.lease),patch.object(c,"close_lease") as close:
            with self.assertRaisesRegex(RuntimeError,"KS_DISCONNECT_LEASE_MISMATCH"):
                c.before_openvpn_disconnect(125,"utun15")
            close.assert_not_called()
            c.before_openvpn_disconnect(123,"utun15")
            close.assert_called_once_with(self.lease)
    def test_unintegrated_engines_do_not_claim_ready(self):
        self.assertEqual(c.SUPPORTED_PROTOCOLS,{"wireguard","amneziawg","openvpn"}|a.TUN_PROTOCOLS)
        for file in ("cisco_openconnect_tunnel.py","cisco_management_route_guard.py",
                     "l2tp_native_system.py","l2tp_management_route_guard.py"):
            text=Path(__file__).with_name(file).read_text()
            self.assertIn("twinconnect-killswitch-control/lease.json",text)
            self.assertIn("KS_RECONNECT_NOT_AUTHORIZED",text)

if __name__=="__main__": unittest.main()
