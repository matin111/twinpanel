"""Metadata-only repair must detect stale port-correct TLS SNI.

No VPN service changes or external network use.
"""
import unittest
from scripts.twinpanel_legacy_xray_metadata_repair_v1 import (
    item_has_complete_profiles,
)


class StaleTlsSniTests(unittest.TestCase):
    REQUIRED = frozenset(("websocket_tls", "xhttp_reality", "tcp_tls"))
    def item(self, ws=26011, xhttp=24011, tcp=28011,
             sni="v2usa.in88.sbs"):
        return {"profiles": [
            {"id":"websocket_tls","uri":f"vless://u@94.183.231.158:{ws}?type=ws&security=tls&sni={sni}"},
            {"id":"xhttp_reality","uri":f"vless://u@94.183.231.158:{xhttp}?type=xhttp&security=reality&sni=www.microsoft.com"},
            {"id":"tcp_tls","uri":f"vless://u@94.183.231.158:{tcp}?type=tcp&security=tls&sni={sni}"},
        ]}

    def test_correct_ports_and_sni_are_complete(self):
        self.assertTrue(item_has_complete_profiles(
            self.item(), self.REQUIRED, 11, "v2usa.in88.sbs",
        ))

    def test_correct_ports_but_old_sni_must_be_repaired(self):
        self.assertFalse(item_has_complete_profiles(
            self.item(sni="tunel.in88.sbs"),
            self.REQUIRED, 11, "v2usa.in88.sbs",
        ))

    def test_old_public_ports_must_be_repaired(self):
        self.assertFalse(item_has_complete_profiles(
            self.item(ws=23311, xhttp=23111),
            self.REQUIRED, 11, "v2usa.in88.sbs",
        ))

    def test_tls_sni_comparison_is_case_insensitive(self):
        self.assertTrue(item_has_complete_profiles(
            self.item(sni="V2USA.IN88.SBS"),
            self.REQUIRED, 11, "v2usa.in88.sbs",
        ))

    def test_no_explicit_sni_preserves_existing_port_behavior(self):
        self.assertTrue(item_has_complete_profiles(
            self.item(sni="tunel.in88.sbs"), self.REQUIRED, 11,
        ))

    def test_domainless_profile_policy_is_untouched(self):
        required=frozenset(("xhttp_reality","tcp_reality","tcp_reality_vision"))
        item={"profiles":[
            {"id":"xhttp_reality","uri":"vless://u@host:23111?type=xhttp&security=reality"},
            {"id":"tcp_reality","uri":"vless://u@host:38011?type=tcp&security=reality"},
            {"id":"tcp_reality_vision","uri":"vless://u@host:39011?type=tcp&security=reality"},
        ]}
        self.assertTrue(item_has_complete_profiles(
            item, required, 11, "v2usa.in88.sbs",
        ))

if __name__=="__main__":
    unittest.main()
