"""Offline Kill Switch rules: no PF load, VPN or network mutation."""
import unittest
from unittest.mock import patch
import unsigned_killswitch_policy as ks

class KillSwitchPolicyTests(unittest.TestCase):
    def test_offline_blocks_both_families_and_only_loopback_is_allowed(self):
        self.assertEqual(ks.render_policy(),
            "pass quick on lo0 all no state\nblock drop quick all\n")

    def test_exact_tunnel_and_transport_allowance(self):
        result = ks.render_policy("utun15", "en0",
            (ks.Transport("1.2.3.4",443,"tcp"), ks.Transport("1.2.3.4",51820,"udp")))
        self.assertIn("pass quick on utun15 all no state",result)
        self.assertIn("to 1.2.3.4 port = 443 user = root",result)
        self.assertIn("to 1.2.3.4 port = 51820 user = root",result)
        self.assertEqual(result.count("keep state (if-bound)"),2)
        self.assertTrue(result.endswith("block drop quick all\n"))
        self.assertNotIn("pass quick on en0 all",result)

    def test_ipv6_is_explicit(self):
        result = ks.render_policy("utun4","en0",
            (ks.Transport("2606:4700:4700::1111",443,"tcp"),))
        self.assertIn("inet6 proto tcp",result)
        self.assertTrue(result.endswith("block drop quick all\n"))

    def test_offline_cannot_keep_exceptions(self):
        with self.assertRaisesRegex(ValueError,"KS_OFFLINE_EXCEPTIONS_REFUSED"):
            ks.render_policy(None,"en0",(ks.Transport("1.2.3.4",443,"tcp"),))

    def test_reject_unverified_interfaces_and_empty_transport(self):
        for value in ("utun","en0","utun15\npass all","ppp"):
            with self.assertRaises(ValueError):
                ks.render_policy(value,"en0",(ks.Transport("1.2.3.4",443,"tcp"),))
        with self.assertRaises(ValueError):
            ks.render_policy("utun15","en0",())
        with self.assertRaises(ValueError):
            ks.render_policy("utun15","any",(ks.Transport("1.2.3.4",443,"tcp"),))

    def test_reject_unsafe_endpoint_or_protocol(self):
        for ip in ("127.0.0.1","192.168.0.1","0.0.0.0","1.2.3.4\npass all","::1"):
            with self.assertRaises(ValueError):
                ks.Transport(ip,443,"tcp")
        for port, proto in ((0,"tcp"),(65536,"tcp"),(True,"tcp"),(443,"any"),(443,"esp")):
            with self.assertRaises(ValueError):
                ks.Transport("1.2.3.4",port,proto)

    def test_only_dry_run_invokes_pf(self):
        with patch.object(ks.subprocess,"run") as run:
            run.return_value.returncode=0
            self.assertTrue(ks.validate_kernel_syntax(ks.render_policy()))
            args=run.call_args.args[0]
            self.assertEqual(args[:5],["/sbin/pfctl","-n","-a",ks.ANCHOR,"-f"])
            self.assertNotIn("-e",args)
            self.assertNotIn("-E",args)

if __name__=="__main__":
    unittest.main()
