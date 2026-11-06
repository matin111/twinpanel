"""V2Ray tunnel delivery must keep ingress routing but expose dedicated domain.

The optional xray_domain is *not* safe to substitute for arbitrary Exit
addresses. Verify its DNS target matches the already-selected Iran ingress.
No certificate, tunnel, database, other-protocol or UUID mutation is allowed.
"""
from __future__ import annotations

import ast
from functools import lru_cache
import ipaddress
from pathlib import Path
import socket
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/app/xray_node_domain_runtime.py"


def runtime():
    tree = ast.parse(SOURCE.read_text(encoding="utf8"))
    names = {
        "_resolved_host_ips",
        "_verified_tunnel_xray_domain",
        "_profile_endpoint_with_dedicated_domain",
        "_customer_profile_endpoint_with_dedicated_domain",
    }
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(funcs) == 4, "production hooks changed"
    originals = {
        "_original_profile_endpoint": lambda db,node,profile: ("tunel2.in88.sbs", {"websocket_tls":26007,"xhttp_reality":24007,"tcp_tls":28007}[profile]),
        "_original_customer_profile_endpoint_v261": lambda db,node,profile,item: ("tunel2.in88.sbs", {"websocket_tls":26007,"xhttp_reality":24007,"tcp_tls":28007}[profile]) if item.get("delivery_mode")!="direct" else ("64.49.12.196", 9444),
        "xray_modern_runtime": SimpleNamespace(_public_port=lambda nid,profile: {"websocket_tls":26000+nid,"xhttp_reality":24000+nid,"tcp_tls":28000+nid}[profile]),
        "_stored_xray_domain": lambda node: str(getattr(node,"xray_domain","") or "").strip().lower(),
        "_profile_uses_tls": lambda profile: profile in ("websocket_tls","tcp_tls"),
        "_dedicated_direct_tls_authority": lambda node,profile,host: node.xray_domain if profile in ("websocket_tls","tcp_tls") and node.xray_domain else host,
        "socket":socket,
        "ipaddress":ipaddress,
        "lru_cache":lru_cache,
        "time":time,
        "Node": object,
        "Session": object,
    }
    exec(compile(ast.Module(body=funcs,type_ignores=[]),str(SOURCE),"exec"),originals)
    return originals


class DedicatedTunnelAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.rt = runtime()
        self.n = SimpleNamespace(id=7,xray_domain="v2ray2.in88.sbs")
        self.addr = {
            "tunel2.in88.sbs": frozenset({"94.183.231.158"}),
            "v2ray2.in88.sbs": frozenset({"94.183.231.158"}),
            "bad-direct-exit.example": frozenset({"176.65.140.83"}),
        }

    def resolve(self, host, bucket):
        return self.addr.get(host,frozenset())

    def test_existing_public_tunnel_ports_all_use_dedicated_domain(self):
        with patch.dict(self.rt,{"_resolved_host_ips":self.resolve}):
            for protocol,port in (("websocket_tls",26007),("xhttp_reality",24007),("tcp_tls",28007)):
                with self.subTest(protocol=protocol):
                    self.assertEqual(self.rt["_profile_endpoint_with_dedicated_domain"](None,self.n,protocol),
                                     ("v2ray2.in88.sbs",port))
                    self.assertEqual(self.rt["_customer_profile_endpoint_with_dedicated_domain"](
                        None,self.n,protocol,{"delivery_mode":"tunnel"}),
                        ("v2ray2.in88.sbs",port))

    def test_legacy_tunnel_and_direct_tls_preserve_semantics(self):
        with patch.dict(self.rt,{"_resolved_host_ips":self.resolve}):
            self.assertEqual(self.rt["_customer_profile_endpoint_with_dedicated_domain"](
                None,self.n,"websocket_tls",{}),("tunel2.in88.sbs",26007))
            self.assertEqual(self.rt["_customer_profile_endpoint_with_dedicated_domain"](
                None,self.n,"websocket_tls",{"delivery_mode":"direct"}),("v2ray2.in88.sbs",9444))
            self.assertEqual(self.rt["_customer_profile_endpoint_with_dedicated_domain"](
                None,self.n,"xhttp_reality",{"delivery_mode":"direct"}),("64.49.12.196",9444))

    def test_wrong_dns_never_changes_tunnel_authority(self):
        self.addr["v2ray2.in88.sbs"] = frozenset({"176.65.140.83"})
        with patch.dict(self.rt,{"_resolved_host_ips":self.resolve}):
            self.assertEqual(self.rt["_customer_profile_endpoint_with_dedicated_domain"](
                None,self.n,"xhttp_reality",{"delivery_mode":"tunnel"}),
                ("tunel2.in88.sbs",24007))
            self.assertEqual(self.rt["_profile_endpoint_with_dedicated_domain"](
                None,self.n,"websocket_tls"),("tunel2.in88.sbs",26007))

    def test_dns_failure_and_ipv6_bypass_are_fail_closed(self):
        with patch.dict(self.rt,{"_resolved_host_ips":lambda host,bucket: frozenset()}):
            self.assertEqual(self.rt["_verified_tunnel_xray_domain"](
                self.n,"tunel2.in88.sbs"),"tunel2.in88.sbs")
        self.addr["v2ray2.in88.sbs"] = frozenset({"94.183.231.158","2001:db8::1234"})
        with patch.dict(self.rt,{"_resolved_host_ips":self.resolve}):
            self.assertEqual(self.rt["_verified_tunnel_xray_domain"](
                self.n,"tunel2.in88.sbs"),"tunel2.in88.sbs")

    def test_missing_dedicated_setting_preserves_generic_tunnel_domain(self):
        self.n.xray_domain=None
        with patch.dict(self.rt,{"_resolved_host_ips":self.resolve}):
            self.assertEqual(self.rt["_verified_tunnel_xray_domain"](
                self.n,"tunel2.in88.sbs"),"tunel2.in88.sbs")

    def test_dns_resolver_returns_all_ipv4_ipv6_addresses(self):
        fake = [
            (socket.AF_INET,socket.SOCK_STREAM,6,"",("94.183.231.158",0)),
            (socket.AF_INET6,socket.SOCK_STREAM,6,"",("2001:db8::1234",0,0,0)),
        ]
        with patch.object(socket,"getaddrinfo",return_value=fake):
            got=self.rt["_resolved_host_ips"]("v2ray2.in88.sbs",1000000001)
        self.assertEqual(got,frozenset({"94.183.231.158","2001:db8::1234"}))

    def test_source_writes_no_data_or_changes_to_tunnel(self):
        src=SOURCE.read_text(encoding="utf8")
        self.assertIn("dedicated_ips.issubset(ingress_ips)",src)
        self.assertIn('mode == "tunnel"',src)
        self.assertIn("if not _profile_uses_tls(profile)",src)
        self.assertNotIn("systemctl restart xray",src)


if __name__=="__main__":
    unittest.main()
