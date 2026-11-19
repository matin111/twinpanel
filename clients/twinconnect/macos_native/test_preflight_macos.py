#!/usr/bin/env python3
"""Unit checks for the read-only TwinConnect macOS preflight."""
import importlib.util
import pathlib
import unittest
from unittest import mock

path = pathlib.Path(__file__).with_name("preflight_macos.py")
spec = importlib.util.spec_from_file_location("twinconnect_macos_preflight", path)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class PreflightTests(unittest.TestCase):
    def test_metal_device_available(self):
        with mock.patch.object(preflight, "command_output", return_value=(0, "TWINCONNECT_METAL_AVAILABLE")):
            self.assertTrue(preflight.metal_available()[0])

    def test_metal_unavailable_fails_closed(self):
        with mock.patch.object(preflight, "command_output", return_value=(0, "TWINCONNECT_METAL_UNAVAILABLE")):
            self.assertFalse(preflight.metal_available()[0])

    def test_metal_tool_error_fails_closed(self):
        with mock.patch.object(preflight, "command_output", return_value=(1, "swift failed")):
            self.assertFalse(preflight.metal_available()[0])

    def test_xcode_15_is_not_sufficient(self):
        with mock.patch.object(preflight, "command_output", return_value=(0, "Xcode 15.4\nBuild version 15F31c")):
            self.assertFalse(preflight.xcode_status()[0])

    def test_xcode_16_is_accepted(self):
        with mock.patch.object(preflight, "command_output", return_value=(0, "Xcode 16.2\nBuild version 16C5032a")):
            self.assertTrue(preflight.xcode_status()[0])

    def test_no_identity_fails_closed(self):
        with mock.patch.object(preflight, "command_output", return_value=(0, "0 valid identities found")):
            self.assertFalse(preflight.signing_status()[0])

    def test_checks_do_not_confuse_metal_and_signing(self):
        with mock.patch.object(preflight.platform, "system", return_value="Darwin"), \
             mock.patch.object(preflight, "metal_available", return_value=(False, "no Metal")), \
             mock.patch.object(preflight, "xcode_status", return_value=(True, "Xcode 16.2")), \
             mock.patch.object(preflight, "signing_status", return_value=(True, "one identity")):
            result = preflight.check_host()
        self.assertFalse(result["gui_ready"])
        self.assertTrue(result["signed_vpn_build_ready"])

    def test_non_macos_host_safe(self):
        with mock.patch.object(preflight.platform, "system", return_value="Linux"):
            result = preflight.check_host()
        self.assertFalse(result["gui_ready"])
        self.assertFalse(result["signed_vpn_build_ready"])


if __name__ == "__main__":
    unittest.main()
