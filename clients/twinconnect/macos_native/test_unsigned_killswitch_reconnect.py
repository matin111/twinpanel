"""Protected same-profile reconnect acceptance contracts. No real PF mutations."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import unsigned_killswitch_console_control as c
import wireguard_management_route_guard as g
import wireguard_unsigned_tunnel as w

class ReconnectTests(unittest.TestCase):
    def setUp(self):
        self.raw="synthetic original profile"
        self.identity={"protocol":"wireguard","digest":hashlib.sha256(self.raw.encode()).hexdigest(),
                       "ip":"1.2.3.4","port":51820,"uplink":"en0",
                       "gateway":"1.2.3.1","baseline_ip":"8.8.4.4"}
        self.lease={"phase":"owned","nonce":"a"*32,"token":"123","locked":True,
                    "canonical":list(c.lines(c.RULES)),"pid":123,"interface":"utun15",
                    "reconnect_identity":self.identity}
    def test_bootstrap_only_exact_root_udp(self):
        rules=c.bootstrap_rules(self.identity)
        self.assertNotIn("utun",rules)
        self.assertIn("on en0 inet proto udp",rules)
        self.assertIn("to 1.2.3.4 port = 51820 user = root",rules)
        self.assertNotIn("proto tcp",rules)
        self.assertTrue(rules.endswith("block drop quick all\n"))
    def test_begin_only_original_profile(self):
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=self.lease),patch.object(c,"replace_owned_policy") as replace:
            with self.assertRaisesRegex(RuntimeError,"WG_KS_ORIGINAL_PROFILE_REQUIRED"):
                c.begin_reconnect("different","wireguard")
            replace.assert_not_called()
    def test_begin_has_deadline_and_no_tunnel_rule(self):
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=self.lease),patch.object(c,"session_deadline",return_value=0),patch.object(c.time,"time",return_value=5000),patch.object(c,"anchor_rules",return_value=c.lines(c.RULES)),patch.object(c,"replace_owned_policy") as replace,patch.object(c,"publish"):
            self.assertEqual(c.begin_reconnect(self.raw,"wireguard"),self.identity)
            self.assertNotIn("utun",replace.call_args.args[1])
            self.assertEqual(replace.call_args.kwargs["reconnect_stage"],"handshake")
    def test_reconnect_timeout_does_not_unlock(self):
        self.lease.update(reconnect_stage="handshake",reconnect_until=4999)
        with patch.object(c,"pf_enabled",return_value=True),patch.object(c,"anchor_rules",return_value=tuple(self.lease["canonical"])),patch.object(c.time,"time",return_value=5000),patch.object(c,"close_lease") as close:
            self.assertEqual(c.monitor_lease(self.lease),"locked")
            close.assert_called_once_with(self.lease)
    def test_attach_requires_actual_worker_and_peer(self):
        self.lease.update(reconnect_stage="handshake",reconnect_until=5060)
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=self.lease),patch.object(c,"session_deadline",return_value=0),patch.object(c.time,"time",return_value=5000),patch.object(c,"process_command",return_value=c.WG_BIN+" -f utun16"),patch.object(c,"wg_uapi",return_value=c.Transport("1.2.3.4",51821,"udp")),patch.object(c,"route_interface",return_value="en0"),patch.object(c,"replace_owned_policy") as replace:
            with self.assertRaisesRegex(RuntimeError,"KS_RECONNECT_PEER_UNVERIFIED"):
                c.attach_reconnect(124,"utun16")
            replace.assert_not_called()
    def test_attach_uses_attested_tunnel_not_old_interface(self):
        self.lease.update(reconnect_stage="handshake",reconnect_until=5060)
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=self.lease),patch.object(c,"session_deadline",return_value=0),patch.object(c.time,"time",return_value=5000),patch.object(c,"process_command",return_value=c.WG_BIN+" -f utun16"),patch.object(c,"wg_uapi",return_value=c.Transport("1.2.3.4",51820,"udp")),patch.object(c,"route_interface",return_value="en0"),patch.object(c,"replace_owned_policy") as replace:
            c.attach_reconnect(124,"utun16")
            self.assertIn("pass quick on utun16 all no state",replace.call_args.args[1])
            self.assertNotIn("utun15",replace.call_args.args[1])
            self.assertEqual(replace.call_args.kwargs["reconnect_stage"],"route")
    def test_amneziawg_requires_its_own_engine_and_uapi(self):
        self.identity["protocol"]="amneziawg"
        self.lease.update(reconnect_stage="handshake",reconnect_until=5060)
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=self.lease),patch.object(c,"session_deadline",return_value=0),patch.object(c.time,"time",return_value=5000),patch.object(c,"process_command",return_value=c.AWG_BIN+" -f utun16") as process,patch.object(c,"wg_uapi",return_value=c.Transport("1.2.3.4",51820,"udp")) as uapi,patch.object(c,"route_interface",return_value="en0"),patch.object(c,"replace_owned_policy") as replace:
            c.attach_reconnect(124,"utun16")
            uapi.assert_called_once_with("amneziawg","utun16")
            replace.assert_called_once()
            process.return_value=c.WG_BIN+" -f utun16"
            replace.reset_mock()
            with self.assertRaisesRegex(RuntimeError,"KS_RECONNECT_PEER_UNVERIFIED"):
                c.attach_reconnect(124,"utun16")
            replace.assert_not_called()
    def test_cannot_switch_protocol_while_locked(self):
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=self.lease),patch.object(c,"replace_owned_policy") as replace:
            with self.assertRaisesRegex(RuntimeError,"WG_KS_ORIGINAL_PROFILE_REQUIRED"):
                c.begin_reconnect(self.raw,"amneziawg")
            replace.assert_not_called()
    def test_close_before_disconnect(self):
        self.lease["locked"]=False
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=self.lease),patch.object(c,"close_lease") as close:
            c.before_wg_disconnect(123,"utun15")
            close.assert_called_once_with(self.lease)
    def test_route_rollback_refused_when_close_fails(self):
        state={"mode":"leased","worker_pid":123,"full_interface":"utun15","interface":"en0","gateway":"1.2.3.1","peers":[]}
        control=MagicMock()
        control.before_wg_disconnect.side_effect=RuntimeError("closed not verified")
        with patch.object(g,"load",return_value=state),patch.object(g,"load_killswitch_control",return_value=control),patch.object(g,"run") as run:
            self.assertEqual(g.rollback(),"WG_KS_CLOSE_BEFORE_ROLLBACK_FAILED")
            run.assert_not_called()
    def test_candidate_pinned_without_dns(self):
        import base64
        key=base64.b64encode(b"a"*32).decode()
        raw=f"[Interface]\nPrivateKey = {key}\nAddress = 10.0.0.2/32\n[Peer]\nPublicKey = {key}\nAllowedIPs = 0.0.0.0/0\nEndpoint = example.invalid:51820\n"
        with patch.object(w.socket,"getaddrinfo") as dns:
            self.assertEqual(w.parse_profile(raw,pinned_endpoint=self.identity)["endpoint"],"1.2.3.4:51820")
            dns.assert_not_called()
    def test_profile_cache_is_memory_only(self):
        source=Path(__file__).with_name("TwinConnectMacOSNativeDashboard.swift").read_text()
        self.assertIn("private var wireGuardReconnectProfile: Data?",source)
        self.assertIn("complete(.success(cached))",source)
        self.assertIn("wireGuardReconnectAccount == session.namespace",source)
        self.assertIn("wireGuardReconnectOrigin == session.apiOrigin",source)
        self.assertIn("wireGuardReconnectServer == serverID",source)
        self.assertIn("wireGuardReconnectProfile = nil",source)

if __name__=="__main__": unittest.main()
