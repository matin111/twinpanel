"""Offline policy tests; no VPN, routes or root commands are executed."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

POLICY = Path(__file__).with_name("unsigned_tun_policy.py")
spec = importlib.util.spec_from_file_location("unsigned_tun_policy", POLICY)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class UnsignedTUNPolicyTests(unittest.TestCase):
    def config(self, root, **overrides):
        obj = {
            "inbounds": [{"type": "tun", "auto_route": True,
                          "auto_redirect": False}],
            "outbounds": [{"type": "anytls", "tag": "proxy"}],
            "route": {"final": "proxy", "auto_detect_interface": True},
        }
        obj.update(overrides)
        file = Path(root) / "client.json"
        file.write_text(json.dumps(obj))
        return file

    def test_config_check_does_not_start_an_engine(self):
        with tempfile.TemporaryDirectory() as root:
            result = policy.validate_full_tun_config(self.config(root))
            self.assertTrue(result["validated"])
            self.assertFalse(result["system_route_modified"])
            self.assertFalse(result["engine_started"])

    def test_rejects_unbound_outbound_routing_loop(self):
        with tempfile.TemporaryDirectory() as root:
            file = self.config(root, route={"final": "proxy"})
            with self.assertRaisesRegex(ValueError, "TUN_OUTBOUND_INTERFACE_BIND_REQUIRED"):
                policy.validate_full_tun_config(file)

    def test_refuses_proxy_only_inbound(self):
        with tempfile.TemporaryDirectory() as root:
            file = self.config(root, inbounds=[
                {"type": "mixed", "listen": "127.0.0.1"}])
            with self.assertRaisesRegex(ValueError, "TUN_INBOUND_REQUIRED"):
                policy.validate_full_tun_config(file)

    def test_refuses_direct_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            file = self.config(root, outbounds=[
                {"type": "direct", "tag": "proxy"}])
            with self.assertRaisesRegex(ValueError, "VPN_OUTBOUND_REQUIRED"):
                policy.validate_full_tun_config(file)

    def test_refuses_route_disabled_and_redirect(self):
        with tempfile.TemporaryDirectory() as root:
            for inbound in (
                {"type": "tun", "auto_route": False},
                {"type": "tun", "auto_route": True, "auto_redirect": True}
            ):
                file = self.config(root, inbounds=[inbound])
                with self.assertRaisesRegex(ValueError, "FULL_TUN_ROUTE_POLICY_INVALID"):
                    policy.validate_full_tun_config(file)

    def test_refuses_symlinked_credentials(self):
        with tempfile.TemporaryDirectory() as root:
            source = self.config(root)
            link = Path(root) / "linked.json"
            link.symlink_to(source)
            with self.assertRaisesRegex(ValueError, "UNTRUSTED_TUN_CONFIGURATION"):
                policy.validate_full_tun_config(link)

    def test_remote_ssh_blocked_even_when_root(self):
        self.assertFalse(policy.local_console_allowed(
            {"SSH_CONNECTION": "x"}, system="Darwin", uid=0))
        self.assertFalse(policy.local_console_allowed(
            {"TWINCONNECT_REMOTE_VPS": "1"}, system="Darwin", uid=0))
        self.assertFalse(policy.local_console_allowed(
            {}, system="Darwin", uid=501))
        self.assertFalse(policy.local_console_allowed(
            {}, system="Linux", uid=0))

    def test_rejects_checkout_and_traversal_as_privileged_binary(self):
        self.assertFalse(policy.trusted_root_file(
            Path("/Users/macvps/twinpanel/sing-box")))
        self.assertFalse(policy.trusted_root_file(
            Path("/Library/PrivilegedHelperTools/TwinConnectTUN/../../tmp/engine")))


if __name__ == "__main__":
    unittest.main()