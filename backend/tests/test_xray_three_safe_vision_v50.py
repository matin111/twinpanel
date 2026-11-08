"""Regression tests for root Xray two-profile fallback and TLS profile loss.

No network, no server mutation, no UUID rotation. Tests ensure every URI
reflects an actual declared modern inbound, not a legacy plaintext fallback.
"""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs,urlsplit

os.environ.setdefault("APP_SECRET_KEY","ci-xray-v50-only")
os.environ.setdefault("DATABASE_URL","sqlite+pysqlite:////tmp/ci-xray-v50.sqlite3")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET","ci-xray-v50-agent")

from app import central_xray_node_authority_v1 as authority
from app import xray_adaptive_three_profiles_v47 as v47
from app import xray_domainless_vision_v50 as vision
from app import xray_hot_client_sync_v1 as hot
from app import xray_bulk_hot_sync_pilot_v1 as bulk

class XrayThreeSafeProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        vision.apply_xray_domainless_vision_v50()

    def setUp(self):
        self.node=SimpleNamespace(id=19,name="uk",xray_domain=None)
        self.db=MagicMock()
        self.db.get.return_value=self.node

    def test_existing_tls_three_profiles_remain_public_even_with_missing_orm_domain(self):
        item={"node_id":19,"tls_available":True,"profiles":[
            {"id":"websocket_tls","uri":"vless://test@tunnel:2419?type=ws&security=tls"},
            {"id":"xhttp_reality","uri":"vless://test@tunnel:2419?type=xhttp&security=reality"},
            {"id":"tcp_tls","uri":"vless://test@tunnel:2419?type=tcp&security=tls"},
        ]}
        with patch.object(v47.policy_v30,"_profile_endpoint_v261",
                          return_value=("203.0.113.19",9447)):
            result=v47._customer_xray_item_v47(self.db,item,include_qr=False)
        self.assertIsNotNone(result)
        self.assertEqual(
            [p["id"] for p in result["profiles"]],
            ["websocket_tls","xhttp_reality","tcp_tls"],
        )

    def test_domainless_three_modern_profiles_visible_and_flow_retained(self):
        item={"node_id":19,"tls_available":False,"profiles":[
            {"id":"xhttp_reality","uri":"vless://test@host:2419?type=xhttp&security=reality"},
            {"id":"tcp_reality","uri":"vless://test@host:3819?type=tcp&security=reality"},
            {"id":vision.PROFILE,
             "uri":"vless://test@host:39019?type=tcp&security=reality&flow=xtls-rprx-vision"},
        ]}
        with patch.object(v47.policy_v30,"_profile_endpoint_v261",
                          return_value=("203.0.113.19",9453)):
            result=v47._customer_xray_item_v47(self.db,item,include_qr=False)
        self.assertEqual(
            [p["id"] for p in result["profiles"]],
            ["xhttp_reality","tcp_reality","tcp_reality_vision"],
        )
        self.assertEqual(
            parse_qs(urlsplit(result["profiles"][-1]["uri"]).query)["flow"],
            ["xtls-rprx-vision"],
        )

    def test_domain_detection_uses_canonical_db_even_without_orm_attribute(self):
        self.db.execute.return_value.scalar.return_value="v2ray1.example.org"
        self.assertEqual(
            v47._effective_domain_from_db(self.db,self.node),
            "v2ray1.example.org",
        )

    def test_tls_node_does_not_receive_false_vision_ingress_route(self):
        self.db.execute.return_value.scalar.return_value="v2ray1.example.org"
        with patch.object(vision,"_original_routes",return_value=[]) as original:
            routes=vision._routes_v50(self.db,self.node,"10.0.0.2")
        self.assertEqual(routes,[])
        original.assert_called_once()

    def test_admin_inventory_uses_verified_tls_domain_from_db(self):
        self.db.execute.return_value.scalar.return_value="v2ray.example.org"
        with (patch.object(vision,"_original_admin_rows",return_value=[]),
              patch.object(vision,"SessionLocal") as session_factory):
            session_factory.return_value.__enter__.return_value=self.db
            rows=vision._admin_rows_v50(self.node,8443)
        self.assertEqual(
            [row["id"] for row in rows],
            ["websocket_tls","xhttp_reality","tcp_tls"],
        )

    def test_mother_route_remains_unchanged(self):
        mother=SimpleNamespace(
            id=1,name="FR",is_mother=True,is_local_core=True,
            agent_url="local://core",
        )
        with patch.object(vision,"_original_routes",return_value=[
            {"protocol":"v2ray","profile":"xhttp_reality"},
        ]):
            routes=vision._routes_v50(self.db,mother,"10.0.0.2")
        self.assertEqual(len(routes),1)

    def test_plaintext_legacy_cannot_become_third_public_profile(self):
        item={"node_id":19,"profiles":[{"id":"tcp_simple","uri":"vless://plain@host:8443"}]}
        with patch.object(v47.policy_v30,"_profile_endpoint_v261") as endpoint:
            self.assertIsNone(v47._customer_xray_item_v47(self.db,item,include_qr=False))
            endpoint.assert_not_called()

    def test_exact_target_public_ports_and_vision_flow(self):
        self.assertEqual(vision.target_port(8443),9453)
        self.assertEqual(vision.public_port(19),39019)
        uri=vision.build_uri(
            client_id="a1b2",host="host.example",port=39019,name="user-uk",
            sni="example.org",public_key="A"*43,short_id="1234",
        )
        query=parse_qs(urlsplit(uri).query)
        self.assertEqual(query["security"],["reality"])
        self.assertEqual(query["type"],["tcp"])
        self.assertEqual(query["flow"],["xtls-rprx-vision"])
        self.assertNotIn("allowInsecure",query)

    def test_remote_installer_uses_handler_service_without_global_restart(self):
        script=vision._install_script(9453)
        self.assertIn('"api","adi"',script)
        self.assertIn('"api","rmi"',script)
        self.assertIn('"run","-test"',script)
        self.assertIn('"flow":FLOW',script)
        self.assertIn("XRAY_VISION_LIVE_VERIFICATION_FAILED",script)
        self.assertNotIn("systemctl restart xray",script)
        self.assertNotIn("systemctl stop xray",script)

    def test_hot_account_sync_adds_vision_flow_only_on_vision_tag(self):
        for remote in (hot._REMOTE,bulk._REMOTE):
            self.assertIn('tag == "vless-tcp-reality-vision"',remote)
            self.assertIn('client["flow"] = "xtls-rprx-vision"',remote)
            self.assertIn("XRAY_VISION_EXISTING_FLOW_MISMATCH",remote)

    def test_public_authority_accepts_two_transitional_or_three_verified_modern(self):
        base={
            "tls_enabled":False,"profiles":["xhttp_reality","tcp_reality"],
            "xhttp_path":"/example",
            "reality_password":"A"*43,
            "reality_server_name":"example.org",
            "short_id_xhttp":"1234",
        }
        self.assertEqual(len(authority.validate_public_authority(base)),2)
        new={**base,"profiles":["xhttp_reality","tcp_reality","tcp_reality_vision"]}
        self.assertEqual(len(authority.validate_public_authority(new)),3)
        unsafe={**base,"profiles":["xhttp_reality","tcp_reality","tcp_simple"]}
        with self.assertRaisesRegex(RuntimeError,"PROFILE_SET_INVALID"):
            authority.validate_public_authority(unsafe)

    def test_node_authority_generates_actual_third_vision_uri(self):
        a={
            "tls_enabled":False,
            "profiles":["xhttp_reality","tcp_reality","tcp_reality_vision"],
            "xhttp_path":"/path","reality_password":"A"*43,
            "reality_server_name":"example.org","short_id_xhttp":"1234",
            "tls_domain":"","tls_sni_ws":"","tls_sni_tcp":"",
        }
        uuid="3980610a-2a75-4977-b2d6-fbd33421026a"
        def endpoint(db,node,key):
            return "203.0.113.19",{"xhttp_reality":29019,"tcp_reality":38019,
                                    "tcp_reality_vision":39019}[key]
        with (patch.object(authority,"_endpoint",side_effect=endpoint),
              patch.object(authority.xr,"_build_uri",
                           return_value="vless://"+uuid+"@host:29019?type=xhttp&security=reality")):
            item=authority.build_item_from_node_authority(
                self.db,self.node,client_uuid=uuid,
                account_label="user-uk",authority=a,
            )
        self.assertEqual([p["id"] for p in item["profiles"]],a["profiles"])
        self.assertIn("flow=xtls-rprx-vision",item["profiles"][-1]["uri"])
        self.assertEqual(item["uuid"],uuid)
        self.assertNotIn("private_key",repr(item))

class XrayVisionPrepareTests(unittest.IsolatedAsyncioTestCase):
    async def test_tls_nodes_skip_vision_and_never_open_port(self):
        with (patch.object(vision.provision,"cmd",new_callable=AsyncMock,
                           return_value='{"ready":false,"reason":"tls_exit_uses_three_tls_profiles"}') as cmd,
              patch.object(vision.provision,"ufw_allow",new_callable=AsyncMock) as firewall):
            state=await vision.prepare_domainless_vision(object(),8443)
        self.assertFalse(state["ready"])
        cmd.assert_awaited_once()
        firewall.assert_not_awaited()

    async def test_third_profile_fails_closed_if_hot_add_unverified(self):
        with (patch.object(vision.provision,"cmd",new_callable=AsyncMock,
                           return_value='{"ready":false,"reason":"not_verified"}'),
              patch.object(vision.provision,"ufw_allow",new_callable=AsyncMock) as firewall):
            with self.assertRaisesRegex(RuntimeError,"NOT_VERIFIED"):
                await vision.prepare_domainless_vision(object(),8443)
        firewall.assert_not_awaited()

    async def test_success_opens_only_the_new_vision_port(self):
        with (patch.object(vision.provision,"cmd",new_callable=AsyncMock,
                           return_value='{"ready":true,"changed":true,"clients":1216}'),
              patch.object(vision.provision,"ufw_allow",new_callable=AsyncMock) as firewall):
            state=await vision.prepare_domainless_vision(object(),8443)
        self.assertTrue(state["ready"])
        self.assertEqual(firewall.await_args.args[1:],(9453,"tcp"))


if __name__=="__main__":
    unittest.main()
