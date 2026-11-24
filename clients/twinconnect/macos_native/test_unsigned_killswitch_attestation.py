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

    def test_unimplemented_guard_is_never_promoted(self):
        for index,reason in ((2,"KS_OPENVPN_TRANSPORT_NOT_ATTESTED"),(3,"KS_L2TP_TRANSPORT_NOT_ATTESTED")):
            states=[None]*4
            states[index]=lease()
            with patch.object(a,"read_guard",side_effect=states):
                with self.assertRaisesRegex(ValueError,reason): a.collect()

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
        config["outbounds"][0].update(type="socks",server="127.0.0.1")
        with patch.object(a,"run",return_value=Mock(returncode=0,stdout="pid = 10")), patch.object(a,"root_private_json",return_value=config), patch.object(a,"route_interface",side_effect=route):
            with self.assertRaisesRegex(ValueError,"KS_SECONDARY_TRANSPORT_NOT_ATTESTED"):
                a.tun_evidence(processes)

if __name__=="__main__": unittest.main()
