"""Regression tests for detached Xray worker's domain-authority binding.

No SSH, DNS updates, user provisioning or VPN service writes.
"""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/twinpanel_central_xray_node_bulk_v1.py"


class CentralXrayDedicatedDomainTests(TestCase):
    def test_detached_worker_maps_domain_before_loading_node(self):
        source=SCRIPT.read_text(encoding="utf-8")
        run=source.split("async def run(",1)[1].split("if __name__",1)[0]
        # Source port bases must match the self-hosted API and TP27 ingress.
        self.assertIn('xr.PROFILE_META[xr.PROFILE_XHTTP]["public_base"] = 24000',run)
        self.assertIn('xr.PROFILE_META[xr.PROFILE_WS]["public_base"] = 26000',run)
        self.assertIn("_activate_xray_install_runtime()",run)
        self.assertLess(run.index("_activate_xray_install_runtime()"),
                        run.index("with SessionLocal() as db:"))

    def test_tcp_reality_uses_verified_domain_only_for_tunnel(self):
        from app.central_xray_node_authority_v1 import _endpoint
        node=SimpleNamespace(id=19,xray_domain="v2uk.in88.sbs")
        with (patch("app.routers.account_delivery._tunnel_access_endpoint",
                    return_value=("185.211.58.12",23019)),
              patch("app.routers.account_delivery._port",return_value=8443),
              patch("app.xray_node_domain_runtime._verified_tunnel_xray_domain",
                    return_value="v2uk.in88.sbs") as verified):
            self.assertEqual(_endpoint(None,node,"tcp_reality"),
                             ("v2uk.in88.sbs",38019))
            self.assertEqual(_endpoint(None,node,"tcp_reality_vision"),
                             ("v2uk.in88.sbs",39019))
            self.assertEqual(verified.call_count,2)

    def test_direct_route_keeps_original_address_and_port(self):
        from app.central_xray_node_authority_v1 import _endpoint
        node=SimpleNamespace(id=22,xray_domain="v2fin.in88.sbs")
        with (patch("app.routers.account_delivery._tunnel_access_endpoint",
                    return_value=("65.109.210.100",8443)),
              patch("app.routers.account_delivery._port",return_value=8443),
              patch("app.xray_node_domain_runtime._verified_tunnel_xray_domain") as verified):
            self.assertEqual(_endpoint(None,node,"tcp_reality"),
                             ("65.109.210.100",9448))
            self.assertEqual(_endpoint(None,node,"tcp_reality_vision"),
                             ("65.109.210.100",9453))
            verified.assert_not_called()

    def test_dns_mismatch_never_forces_domain(self):
        from app.xray_node_domain_runtime import _verified_tunnel_xray_domain
        node=SimpleNamespace(xray_domain="v2fin.in88.sbs")
        with patch("app.xray_node_domain_runtime._resolved_host_ips",
                   side_effect=[frozenset({"185.211.58.12"}),
                                frozenset({"65.109.210.100"})]):
            self.assertEqual(
                _verified_tunnel_xray_domain(node,"185.211.58.12"),
                "185.211.58.12",
            )


if __name__=="__main__":
    import unittest
    unittest.main()
