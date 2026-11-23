"""Offline unit tests for L2TP system orchestrator; no OS network mutations."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "l2tp_native_system", Path(__file__).with_name("l2tp_native_system.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NativeSystemTests(unittest.TestCase):
    def test_invalid_json_rejected_without_route_operation(self):
        with patch.object(module, "guard") as guard:
            with self.assertRaisesRegex(ValueError, "L2TP_PROFILE_INVALID_JSON"):
                module.parse_profile(b"not json")
            guard.assert_not_called()

    def test_short_input_rejected(self):
        with patch.object(module, "guard") as guard:
            with self.assertRaisesRegex(ValueError, "L2TP_PROFILE_INVALID_SIZE"):
                module.parse_profile(b"{}")
            guard.assert_not_called()

    def test_private_dns_rejected(self):
        with patch.object(module.socket, "getaddrinfo", return_value=[
                (None, None, None, None, ("127.0.0.1", 0))]):
            with self.assertRaisesRegex(ValueError, "L2TP_REMOTE_ENDPOINT_UNSAFE"):
                module.resolved_endpoint("local.internal")

    def test_probe_cannot_succeed_without_independent_verification(self):
        def reply(*args, **kwargs):
            if args[0] == "probe-host":
                return "L2TP_PROBE_HOST_ACTIVE"
            if args[0] == "verify-probe":
                raise ValueError("L2TP_VPN_EXIT_NOT_VERIFIED")
            return "L2TP_PROBE_ROLLBACK_VERIFIED"
        with patch.object(module, "guard", side_effect=reply) as guard:
            with self.assertRaisesRegex(ValueError, "L2TP_VPN_EXIT_NOT_VERIFIED"):
                module.check_probe("ppp0", "1.1.1.1")
            self.assertEqual(guard.call_args_list[-1].args[0], "rollback-probe")

    def test_no_full_connect_without_preflight(self):
        with patch.object(module, "guard", return_value="L2TP_OTHER_SYSTEM_VPN_ACTIVE"), \
             patch.object(module, "native") as native:
            with self.assertRaisesRegex(ValueError, "L2TP_PREFLIGHT_FAILED"):
                module.full_connection({"server": "vpn.example.com"})
            native.assert_not_called()


if __name__ == "__main__":
    unittest.main()
