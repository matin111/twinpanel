"""Offline Sudoku profile and two-engine attestation tests."""
import json
from pathlib import Path
import unittest
from unittest import mock
import unsigned_sudoku_profile as sdk
import unsigned_tun_daemon as daemon

def sample():
    return {"mode":"client","transport":"tcp","server_address":"example.org:12345",
            "key":"a"*64,"aead":"chacha20-poly1305","ascii":"prefer_entropy",
            "padding_min":5,"padding_max":15,"enable_pure_downlink":True,
            "multiplex":"off","httpmask":{"disable":False,"mode":"auto"}}

class SudokuTests(unittest.TestCase):
    def test_preserves_port_key_cipher_and_loopback_only(self):
        data=sample()
        data.update({"local_address":"0.0.0.0","rule_urls":["https://example.invalid/list"]})
        with mock.patch.object(sdk.socket, "getaddrinfo", return_value=[
                (None,None,None,None,("1.2.3.4",12345))]):
            raw, ips = sdk.sudoku_runtime(json.dumps(data))
        item=json.loads(raw)
        self.assertEqual(ips,("1.2.3.4",))
        self.assertEqual(item["server_address"],"1.2.3.4:12345")
        self.assertEqual(item["key"],data["key"])
        self.assertEqual(item["local_address"],"127.0.0.1")
        self.assertEqual(item["rule_urls"],["global"])
        self.assertEqual(sdk.sudoku_singbox_tun()["outbounds"][0]["server_port"],
                         item["local_port"])
    def test_rejects_bad_security_and_duplicate_keys(self):
        for bad in ({"mode":"server"},{"key":"bad"},{"aead":"none"},
                    {"padding_max":101},{"httpmask":{"disable":True,"mode":"auto"}}):
            data=sample()
            data.update(bad)
            with self.assertRaisesRegex(ValueError,"SUDOKU_PROFILE_INVALID"):
                sdk.sudoku_runtime(json.dumps(data))
        with self.assertRaisesRegex(ValueError,"SUDOKU_PROFILE_INVALID"):
            sdk.sudoku_runtime('{"mode":"client","mode":"server"}')
    def test_refuses_private_endpoint(self):
        with mock.patch.object(sdk.socket,"getaddrinfo",return_value=[
                (None,None,None,None,("127.0.0.1",12345))]):
            with self.assertRaisesRegex(ValueError,"SUDOKU_ENDPOINT_NOT_PUBLIC"):
                sdk.sudoku_runtime(json.dumps(sample()))
    def test_attests_actual_sudoku_not_socks_or_trusttunnel(self):
        session=daemon.Session()
        session.process=mock.Mock(poll=mock.Mock(return_value=None))
        session.transport_process=mock.Mock(poll=mock.Mock(return_value=None))
        session.transport_protocol="sudoku"
        session.owner=502
        with mock.patch.object(session,"console_owner_present",return_value=True), mock.patch.object(
                daemon,"observe_route",return_value={"route_state":"utun_route_observed_unverified"}):
            state=session.status()
        self.assertEqual(state["protocol_code"],"sudoku")
        self.assertFalse(state["system_vpn_verified"])
    def test_native_ui_contract(self):
        ui=Path(__file__).with_name("TwinConnectMacOSNativeDashboard.swift").read_text()
        directory=Path(__file__).with_name("TwinConnectMacOSNativeDirectory.swift").read_text()
        self.assertIn('directory.prepareSudokuProfile(',ui)
        self.assertIn('"sudoku-json"',directory)
        self.assertIn('return "Sudoku"',ui)

if __name__ == "__main__":
    unittest.main()
