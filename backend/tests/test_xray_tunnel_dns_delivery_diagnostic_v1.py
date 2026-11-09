"""Fail-closed, read-only DNS explanation for all TLS Exit nodes.

The public subscription must not use a dedicated hostname resolving to the
wrong Exit. The administrator should see WHY, with the exact Iran ingress.
"""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from app import xray_node_domain_runtime as runtime


class TunnelDnsDeliveryTests(TestCase):
    def node(self, nid=11, domain="v2usa.in88.sbs"):
        return SimpleNamespace(id=nid, xray_domain=domain,
                               public_domain="usa.in88.sbs")

    def check(self, node, port, host, ips, resolved):
        def fake_dns(value, _bucket):
            return frozenset(ips if value == host else resolved)
        with (
            patch.object(runtime, "_original_profile_endpoint",
                         return_value=(host, port)),
            patch.object(runtime, "_resolved_host_ips",
                         side_effect=fake_dns),
            patch.object(runtime.xray_modern_runtime, "_public_port",
                         return_value=24000 + node.id),
        ):
            return runtime._xray_tunnel_dns_diagnostic(MagicMock(),node)

    def test_usa_exit_dns_mismatch_explains_safe_ingress_ip(self):
        result=self.check(
            self.node(),24011,"94.183.231.158",
            {"94.183.231.158"},{"64.49.12.196"},
        )
        self.assertEqual(result["status"],"mismatch")
        self.assertEqual(result["client_address"],"94.183.231.158")
        self.assertEqual(result["suggested_a_record"],"94.183.231.158")
        self.assertEqual(result["observed_domain_ips"],["64.49.12.196"])

    def test_second_germany_exit_mismatch_uses_its_own_iran_ingress(self):
        result=self.check(
            self.node(13,"v2de.in88.sbs"),24013,"193.39.9.222",
            {"193.39.9.222"},{"45.13.226.145"},
        )
        self.assertEqual(result["status"],"mismatch")
        self.assertEqual(result["suggested_a_record"],"193.39.9.222")
        self.assertEqual(result["client_address"],"193.39.9.222")

    def test_matching_dns_shows_domain_without_any_config_change(self):
        result=self.check(
            self.node(),24011,"94.183.231.158",
            {"94.183.231.158"},{"94.183.231.158"},
        )
        self.assertEqual(result["status"],"matched")
        self.assertEqual(result["client_address"],"v2usa.in88.sbs")

    def test_unresolved_dns_fails_closed(self):
        result=self.check(
            self.node(),24011,"94.183.231.158",
            {"94.183.231.158"},set(),
        )
        self.assertEqual(result["status"],"unresolved")
        self.assertEqual(result["client_address"],"94.183.231.158")

    def test_direct_node_keeps_direct_identity_without_guessing_tunnel(self):
        result=self.check(
            self.node(),9447,"64.49.12.196",
            {"64.49.12.196"},{"64.49.12.196"},
        )
        self.assertEqual(result["status"],"direct")
        self.assertEqual(result["mode"],"direct")

    def test_no_dedicated_domain_does_not_invent_dns(self):
        self.assertEqual(
            runtime._xray_tunnel_dns_diagnostic(
                MagicMock(),self.node(domain=None),
            )["status"],"not_configured",
        )

    def test_unavailable_tunnel_resolver_cannot_generate_false_match(self):
        with patch.object(runtime,"_original_profile_endpoint",
                          side_effect=RuntimeError("OFFLINE")):
            result=runtime._xray_tunnel_dns_diagnostic(
                MagicMock(),self.node(),
            )
        self.assertEqual(result["status"],"unavailable")
        self.assertIsNone(result["suggested_a_record"])


if __name__=="__main__":
    import unittest
    unittest.main()
