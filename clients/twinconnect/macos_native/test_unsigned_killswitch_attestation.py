"""Engine evidence contracts. No root, sockets, routes or PF changes."""
import time
import unittest
from unittest.mock import patch, Mock
import unsigned_killswitch_attestation as a

def lease(**overrides):
    state={"mode":"leased","deadline":time.time()+60,"full_interface":"utun15",
           "interface":"en0","worker_pid":123,"endpoint":"1.2.3.4"}
    state.update(overrides)
    return state

def route(destination):
    return "en0" if destination=="1.2.3.4" else "utun15"

class AttestationTests(unittest.TestCase):
    def test_wireguard_and_amnezia_exact_transport(self):
        for protocol,binary in (("wireguard",a.WG_BIN),("amneziawg",a.AWG_BIN)):
            with patch.object(a,"route_interface",side_effect=route), patch.object(a,"process_command",return_value=binary+" -f utun15"), patch.object(a,"wg_uapi",return_value=a.Transport("1.2.3.4",51820,"udp")):
                item=a.wireguard_evidence(lease(protocol_code=protocol))
                self.assertEqual(item.protocol,protocol)
                self.assertIn("to 1.2.3.4 port = 51820 user = root",item.rules())

    def test_expired_or_nonleased_rejected(self):
        for data in (lease(deadline=time.time()-1),lease(mode="trial-full"),lease(deadline=float("inf"))):
            with self.assertRaises(ValueError): a.wireguard_evidence(data)

    def test_route_and_process_identity(self):
        with patch.object(a,"route_interface",return_value="en0"):
            with self.assertRaisesRegex(ValueError,"KS_TUNNEL_ROUTE_UNVERIFIED"):
                a.wireguard_evidence(lease())
        with patch.object(a,"route_interface",side_effect=route), patch.object(a,"process_command",return_value="wireguard-go -f utun15"):
            with self.assertRaisesRegex(ValueError,"KS_ENGINE_IDENTITY_UNVERIFIED"):
                a.wireguard_evidence(lease())

    def test_endpoint_change_refused(self):
        with patch.object(a,"route_interface",side_effect=route), patch.object(a,"process_command",return_value=a.WG_BIN+" -f utun15"), patch.object(a,"wg_uapi",return_value=a.Transport("8.8.8.8",51820,"udp")):
            with self.assertRaisesRegex(ValueError,"KS_TRANSPORT_ENDPOINT_CHANGED"):
                a.wireguard_evidence(lease())

    def test_cisco_exact_tcp_but_dtls_refused(self):
        tcp=Mock(returncode=0,stdout="COMMAND PID USER ...\nopenconnect 123 root TCP 10.0.0.1:52000->1.2.3.4:443 (ESTABLISHED)\n")
        with patch.object(a,"route_interface",side_effect=route), patch.object(a,"process_command",return_value=a.CISCO_BIN+" -b"), patch.object(a,"run",side_effect=[tcp,Mock(returncode=1,stdout="")]):
            self.assertEqual(a.cisco_evidence(lease()).transports[0].port,443)
        with patch.object(a,"route_interface",side_effect=route), patch.object(a,"process_command",return_value=a.CISCO_BIN+" -b"), patch.object(a,"run",side_effect=[tcp,Mock(returncode=0,stdout="HEADER\nUDP CONNECTION\n")]):
            with self.assertRaisesRegex(ValueError,"KS_CISCO_DTLS_NOT_ATTESTED"):
                a.cisco_evidence(lease())

    def test_no_engine_or_ambiguous_engine(self):
        with patch.object(a,"read_guard",return_value=None), patch.object(a,"observed_tun_processes",return_value={}), patch.object(a,"run",return_value=Mock(returncode=1,stdout="")):
            self.assertIsNone(a.collect())
        with patch.object(a,"read_guard",return_value=lease()):
            with self.assertRaisesRegex(ValueError,"KS_MULTIPLE_ENGINE_GUARDS"):
                a.collect()

    def test_invalid_l2tp_guard_is_never_promoted(self):
        states=[None]*4
        states[3]=lease()
        with patch.object(a,"read_guard",side_effect=states):
            with self.assertRaisesRegex(ValueError,"KS_L2TP_INTERFACE_INVALID"): a.collect()

    def test_openvpn_guard_requires_actual_session(self):
        with patch.object(a,"openvpn_session_evidence",side_effect=ValueError("KS_OPENVPN_SOCKET_UNVERIFIED")):
            with self.assertRaisesRegex(ValueError,"KS_OPENVPN_SOCKET_UNVERIFIED"):
                a.openvpn_evidence(lease())
        evidence=a.Evidence("openvpn","utun15","en0",(a.Transport("1.2.3.4",1194,"udp"),),124)
        state=lease(interface="utun15",original_interface="en0")
        with patch.object(a,"openvpn_session_evidence",return_value=(evidence,123,"a"*64)),patch.object(a,"route_interface",side_effect=route):
            self.assertEqual(a.openvpn_evidence(state),evidence)
            state["worker_pid"]=125
            with self.assertRaisesRegex(ValueError,"KS_OPENVPN_ROUTE_UNVERIFIED"):
                a.openvpn_evidence(state)

    def test_common_tun_protocol_map(self):
        for kind,expected in (("vless","v2ray"),("hysteria2","hysteria2"),("tuic","tuic"),
                              ("anytls","anytls"),("socks","socks5"),("snell","snell"),
                              ("naive","naive"),("mieru","mieru")):
            config={"route":{"final":"proxy"},"outbounds":[{"type":kind,"tag":"proxy",
                    "server":"1.2.3.4","server_port":443,"network":"tcp","transport":"TCP"}]}
            self.assertEqual(a.modern_outbound(config)[0],expected)
        self.assertEqual(a.modern_outbound({"route":{"final":"proxy"},"outbounds":[
            {"type":"shadowsocks","tag":"proxy","detour":"shadowtls-transport"},
            {"type":"shadowtls","tag":"shadowtls-transport"}]})[0],"shadowtls")
        with self.assertRaises(ValueError):
            a.modern_outbound({"route":{"final":"direct"},"outbounds":[{"type":"direct"}]})

    def test_real_engine_identity_and_exact_peer_required(self):
        path=str(a.TUN_ROOT/"active-0123456789abcdef0123456789abcdef.json")
        processes={10:(1,"/usr/bin/python3 "+str(a.TUN_ROOT/"unsigned_tun_daemon.py")),
                   11:(10,str(a.TUN_ROOT/"sing-box")+" run -c "+path)}
        config={"route":{"final":"proxy"},"outbounds":[{"type":"vless","tag":"proxy","server":"1.2.3.4","server_port":443}]}
        with patch.object(a,"run",return_value=Mock(returncode=0,stdout="pid = 10")), patch.object(a,"root_private_json",return_value=config), patch.object(a,"route_interface",side_effect=route), patch.object(a,"live_peers",return_value={a.Transport("1.2.3.4",443,"tcp")}):
            self.assertEqual(a.tun_evidence(processes).protocol,"v2ray")
        with patch.object(a,"run",return_value=Mock(returncode=0,stdout="pid = 10")), patch.object(a,"root_private_json",return_value=config), patch.object(a,"route_interface",side_effect=route), patch.object(a,"live_peers",return_value=set()):
            with self.assertRaisesRegex(ValueError,"KS_TUN_TRANSPORT_UNATTESTED"):
                a.tun_evidence(processes)
        config["outbounds"][0].update(type="socks",server="127.0.0.1",network="tcp")
        with patch.object(a,"run",return_value=Mock(returncode=0,stdout="pid = 10")), patch.object(a,"root_private_json",return_value=config), patch.object(a,"route_interface",side_effect=route):
            with self.assertRaisesRegex(ValueError,"KS_SECONDARY_TRANSPORT_NOT_ATTESTED"):
                a.tun_evidence(processes)

    def test_secondary_sudoku_matches_root_child_and_pinned_tcp_peer(self):
        path=a.TUN_ROOT/"active-0123456789abcdef0123456789abcdef.json"
        processes={12:(10,str(a.TUN_ROOT/"sudoku")+" -c "+str(path.with_suffix(".sudoku.json")))}
        profile={"mode":"client","transport":"tcp","local_address":"127.0.0.1","server_address":"1.2.3.4:443"}
        with patch.object(a,"root_private_json",return_value=profile), patch.object(a,"route_interface",side_effect=route), patch.object(a,"live_peers",side_effect=[{a.Transport("1.2.3.4",443,"tcp")},set()]):
            self.assertEqual(a.secondary_evidence(processes,10,11,path,"utun15").protocol,"sudoku")
        with patch.object(a,"root_private_json",return_value=profile), patch.object(a,"live_peers",return_value={a.Transport("8.8.8.8",443,"tcp")}):
            with self.assertRaises(ValueError):
                a.secondary_evidence(processes,10,11,path,"utun15")

    def test_secondary_trusttunnel_uses_only_verified_http2_profile(self):
        path=a.TUN_ROOT/"active-0123456789abcdef0123456789abcdef.json"
        processes={12:(10,str(a.TUN_ROOT/"trusttunnel_client")+" --config "+str(path.with_suffix(".tt.toml"))+" --loglevel error")}
        raw=b'[endpoint]\naddresses = ["1.2.3.4:443"]\nskip_verification = false\nupstream_protocol = "http2"\n[listener.socks]\n'
        with patch.object(a,"root_private_bytes",return_value=raw), patch.object(a,"route_interface",side_effect=route), patch.object(a,"live_peers",side_effect=[{a.Transport("1.2.3.4",443,"tcp")},set()]):
            self.assertEqual(a.secondary_evidence(processes,10,11,path,"utun15").protocol,"trusttunnel")

if __name__=="__main__": unittest.main()
