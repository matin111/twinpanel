"""Offline contracts for shared root-owned TUN protection; no kernel writes."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,MagicMock
import unsigned_killswitch_attestation as a
import unsigned_killswitch_console_control as c
import unsigned_tun_daemon as d

class TunProtectionTests(unittest.TestCase):
    def setUp(self):
        self.peer=a.Transport("1.2.3.4",443,"tcp")
        self.evidence=a.Evidence("v2ray","utun16","en0",(self.peer,),125)
        self.identity={"protocol":"v2ray","digest":"a"*64,"ip":"1.2.3.4","port":443,
                       "transport":"tcp","uplink":"en0","primary_pid":125}
        self.lease={"phase":"owned","locked":True,"reconnect_stage":"handshake",
                    "reconnect_until":5060,"route_worker":123,"pid":123,
                    "interface":"utun15","reconnect_identity":self.identity,
                    "canonical":list(c.lines(c.RULES))}
    def test_all_eleven_candidates_share_one_protocol_adapter(self):
        self.assertEqual(len(a.TUN_PROTOCOLS),11)
        self.assertTrue(a.TUN_PROTOCOLS.issubset(c.SUPPORTED_PROTOCOLS))
        self.assertEqual(d.candidate_protocol({"outbounds":[{"type":"vless"}]}),"v2ray")
        self.assertEqual(d.candidate_protocol({"mode":"trusttunnel"}),"trusttunnel")
        self.assertEqual(d.candidate_protocol({"mode":"sudoku"}),"sudoku")
        self.assertIsNone(d.candidate_protocol({"outbounds":[{"type":"direct"}]}))
    def test_metadata_is_private_and_does_not_contain_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"active-test.json"
            path.write_bytes(b"private synthetic config")
            meta=d.write_session_meta(path,501,125,"a"*64)
            self.assertEqual(meta.name,"active-test.meta")
            self.assertEqual(meta.stat().st_mode&0o777,0o600)
            text=meta.read_text()
            self.assertNotIn("private synthetic config",text)
            self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(),text)
    def test_meta_config_binding(self):
        path=Path("/synthetic/active-test.json")
        raw=b"synthetic reviewed config"
        meta={"owner":501,"primary_pid":125,"digest":"a"*64,
              "config_sha256":hashlib.sha256(raw).hexdigest()}
        with patch.object(a,"observed_tun_processes",return_value={}),patch.object(a,"tun_evidence",return_value=(self.evidence,path,125)),patch.object(a,"root_private_json",return_value=meta),patch.object(a,"root_private_bytes",return_value=raw),patch.object(a.os,"stat",return_value=SimpleNamespace(st_uid=501)):
            self.assertEqual(a.tun_session_identity(False)[1],self.identity)
            meta["owner"]=502
            with self.assertRaisesRegex(ValueError,"KS_TUN_PROFILE_UNVERIFIED"):
                a.tun_session_identity(False)
    def test_only_matching_profile_and_worker_attach(self):
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=self.lease),patch.object(c,"session_deadline",return_value=0),patch.object(c.time,"time",return_value=5000),patch.object(c,"tun_session_identity",return_value=(self.evidence,self.identity)),patch.object(c,"replace_owned_policy") as replace:
            with self.assertRaisesRegex(RuntimeError,"KS_RECONNECT_PEER_UNVERIFIED"):
                c.attach_tun_reconnect(126)
            replace.assert_not_called()
            self.assertEqual(c.attach_tun_reconnect(125),(125,"utun16"))
            self.assertIn("pass quick on utun16 all no state",replace.call_args.args[1])
            self.assertEqual(replace.call_args.kwargs["route_worker"],125)
    def test_close_before_engine_stop(self):
        self.lease.update(locked=False,reconnect_stage=None)
        with patch.object(c,"lock",return_value=MagicMock()),patch.object(c,"read_json",return_value=self.lease),patch.object(c,"close_lease") as close:
            with self.assertRaisesRegex(RuntimeError,"KS_DISCONNECT_LEASE_MISMATCH"):
                c.before_tun_disconnect(999)
            close.assert_not_called()
            c.before_tun_disconnect(123)
            close.assert_called_once_with(self.lease)
    def test_dns_failure_never_promotes_active(self):
        with patch.object(c,"tun_matches_lease",return_value=True),patch.object(c,"run",return_value=SimpleNamespace(returncode=1,stdout="")) as run:
            self.assertFalse(c.tun_network_verified(self.lease))
            self.assertEqual(run.call_count,1)
    def test_named_https_requires_post_probe_route_check(self):
        with patch.object(c,"tun_matches_lease",side_effect=[True,False]),patch.object(c,"run",return_value=SimpleNamespace(returncode=0,stdout="1.2.3.4")):
            self.assertFalse(c.tun_network_verified(self.lease))
    def test_no_direct_dns_or_management_exclusion_in_protected_candidate(self):
        config={"inbounds":[{"type":"tun","route_exclude_address":["8.8.8.8/32"]}],"outbounds":[]}
        updated=d.pinned_reconnect_profile(config,self.identity)
        self.assertEqual(updated["inbounds"][0]["route_exclude_address"],["1.2.3.4/32"])
        self.assertEqual(config["inbounds"][0]["route_exclude_address"],["8.8.8.8/32"])
    def test_hostname_pin_preserves_tls_and_ws_identity(self):
        config={"outbounds":[{"type":"vless","tag":"proxy","server":"vpn.example.com",
                   "server_port":443,"tls":{"enabled":True,"server_name":"tls.example.com"},
                   "transport":{"type":"ws","path":"/test","headers":{"Host":"ws.example.com"}}}]}
        with patch.object(d.socket,"getaddrinfo",return_value=[(2,1,6,"",("1.2.3.4",443))]):
            pinned=d.pin_reviewed_endpoint(config,"v2ray")
        self.assertEqual(pinned["outbounds"][0]["server"],"1.2.3.4")
        self.assertEqual(pinned["outbounds"][0]["tls"],config["outbounds"][0]["tls"])
        self.assertEqual(pinned["outbounds"][0]["transport"],config["outbounds"][0]["transport"])
        self.assertEqual(config["outbounds"][0]["server"],"vpn.example.com")
    def test_all_single_outbound_kinds_pin_before_tun(self):
        for kind,protocol in (("vless","v2ray"),("hysteria2","hysteria2"),("tuic","tuic"),
                    ("anytls","anytls"),("socks","socks5"),("snell","snell"),
                    ("naive","naive"),("mieru","mieru")):
            config={"outbounds":[{"type":kind,"tag":"proxy","server":"vpn.example.com",
                       "server_port":443,"tls":{"enabled":True}}]}
            with patch.object(d.socket,"getaddrinfo",return_value=[(2,1,6,"",("1.2.3.4",443))]):
                pinned=d.pin_reviewed_endpoint(config,protocol)
            self.assertEqual(pinned["outbounds"][0]["server"],"1.2.3.4")
            self.assertEqual(pinned["outbounds"][0]["tls"]["server_name"],"vpn.example.com")
    def test_shadowtls_pins_only_outer_transport(self):
        config={"outbounds":[{"type":"shadowsocks","tag":"proxy","detour":"shadowtls-transport"},
                 {"type":"shadowtls","tag":"shadowtls-transport","server":"vpn.example.com",
                  "server_port":443,"tls":{"enabled":True,"server_name":"tls.example.com"}}]}
        with patch.object(d.socket,"getaddrinfo",return_value=[(2,1,6,"",("1.2.3.4",443))]):
            pinned=d.pin_reviewed_endpoint(config,"shadowtls")
        self.assertEqual(pinned["outbounds"][0],config["outbounds"][0])
        self.assertEqual(pinned["outbounds"][1]["server"],"1.2.3.4")
    def test_private_dns_result_is_rejected(self):
        config={"outbounds":[{"tag":"proxy","server":"vpn.example.com","server_port":443}]}
        with patch.object(d.socket,"getaddrinfo",return_value=[(2,1,6,"",("127.0.0.1",443))]):
            with self.assertRaisesRegex(ValueError,"TUN_KS_ENDPOINT_INVALID"):
                d.pin_reviewed_endpoint(config,"v2ray")
    def test_reviewed_inner_sockets_never_become_outer_exceptions(self):
        output="TCP 172.19.0.1:1234->172.19.0.2:5678 (ESTABLISHED)\nTCP 2.3.4.5:1234->1.2.3.4:443 (ESTABLISHED)"
        with patch.object(a,"run",side_effect=[SimpleNamespace(returncode=0,stdout=output),SimpleNamespace(returncode=1,stdout="")]),patch.object(a,"route_interface",return_value="utun16"):
            self.assertEqual(a.live_peers(125,"utun16"),{self.peer})
    def test_private_socket_off_tun_is_not_ignored(self):
        output="TCP 172.19.0.1:1234->172.19.0.2:5678 (ESTABLISHED)"
        with patch.object(a,"run",return_value=SimpleNamespace(returncode=0,stdout=output)),patch.object(a,"route_interface",return_value="en0"):
            with self.assertRaisesRegex(ValueError,"KS_ENDPOINT_INVALID"):
                a.live_peers(125,"utun16")
    def test_private_socket_outside_reviewed_subnet_is_not_ignored(self):
        output="TCP 172.19.0.1:1234->192.168.1.2:5678 (ESTABLISHED)"
        with patch.object(a,"run",return_value=SimpleNamespace(returncode=0,stdout=output)),patch.object(a,"route_interface",return_value="utun16"):
            with self.assertRaisesRegex(ValueError,"KS_ENDPOINT_INVALID"):
                a.live_peers(125,"utun16")
    def test_ordinary_tun_has_exact_endpoint_exclusion(self):
        config={"inbounds":[{"type":"tun"}],"outbounds":[{"tag":"proxy","server":"1.2.3.4","server_port":443}]}
        endpoints=d.reviewed_endpoint_ips(config,"v2ray")
        self.assertEqual(endpoints,("1.2.3.4",))
        guarded=d.guard_candidate(config,peers=("8.8.8.8",),endpoint_ips=endpoints)
        self.assertEqual(set(guarded["inbounds"][0]["route_exclude_address"]),{"1.2.3.4/32","8.8.8.8/32"})
    def test_other_profile_refused_before_bootstrap(self):
        session=d.Session()
        session.ks_cache={"uid":501,"digest":"b"*64,"protocol":"v2ray"}
        control=MagicMock()
        with patch.object(session,"status",return_value={"state":"stopped"}),patch.object(d,"kill_switch_control",return_value=control):
            with self.assertRaisesRegex(ValueError,"TUN_KS_RECONNECT_NOT_AUTHORIZED"):
                session.start(501,{"outbounds":[{"type":"vless"}]})
            control.begin_reconnect.assert_not_called()

if __name__=="__main__": unittest.main()
