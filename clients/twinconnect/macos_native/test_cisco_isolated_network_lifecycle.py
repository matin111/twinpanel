"""Isolated Cisco/macOS lifecycle tests: never invoke real networksetup or route.

The mock macOS uplink starts with Manual IPv4, a gateway and DNS.
VPN transitions may corrupt the interface state as in the previous incident.
All subprocess/network effects stay inside an in-memory simulated machine.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "cisco_network_recovery_isolated",
    HERE / "cisco_network_recovery.py",
)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)

BASELINE = {
    "version": 1,
    "interface": "en0",
    "service": "Ethernet",
    "mode": "manual",
    "ip": "198.51.100.36",
    "mask": "255.255.255.240",
    "gateway": "198.51.100.33",
    "dns": ["198.51.100.19"],
}


class SimulatedMac:
    def __init__(self):
        self.mode = "manual"
        self.ip = BASELINE["ip"]
        self.mask = BASELINE["mask"]
        self.gateway = BASELINE["gateway"]
        self.dns = list(BASELINE["dns"])
        self.route_gateway = BASELINE["gateway"]
        self.route_interface = "en0"
        self.operations = []

    def vpn_mutates_network(self):
        self.mode = "dhcp"
        self.ip = "169.254.111.69"
        self.mask = "255.255.0.0"
        self.gateway = "(null)"
        self.dns = ["10.0.0.53"]
        self.route_gateway = "10.0.0.1"
        self.route_interface = "utun4"

    def vpn_route_ends(self):
        # VPN script tears down its route, before the recovery tool checks.
        self.route_gateway = BASELINE["gateway"]
        self.route_interface = "en0"

    def command(self, *args):
        self.operations.append(args)
        if args == (recovery.ROUTE, "-n", "get", "default"):
            return (f"route to: default\n"
                    f"gateway: {self.route_gateway}\n"
                    f"interface: {self.route_interface}\n")
        if args == (recovery.NETWORKSETUP, "-listnetworkserviceorder"):
            return "(1) Ethernet\n(Hardware Port: Ethernet, Device: en0)\n"
        if args == (recovery.NETWORKSETUP, "-getinfo", "Ethernet"):
            headline = "Manual Configuration" if self.mode == "manual" else "DHCP Configuration"
            return (f"{headline}\nIP address: {self.ip}\n"
                    f"Subnet mask: {self.mask}\nRouter: {self.gateway}\n")
        if args == (recovery.NETWORKSETUP, "-getdnsservers", "Ethernet"):
            return "\n".join(self.dns) + "\n" if self.dns else "There aren't any DNS Servers set on Ethernet.\n"
        if args[:3] == (recovery.NETWORKSETUP, "-setmanual", "Ethernet"):
            self.mode = "manual"
            self.ip, self.mask, self.gateway = args[3:]
            return ""
        if args == (recovery.NETWORKSETUP, "-setdhcp", "Ethernet"):
            self.mode = "dhcp"
            return ""
        if args[:3] == (recovery.NETWORKSETUP, "-setdnsservers", "Ethernet"):
            self.dns = [] if args[3:] == ("Empty",) else list(args[3:])
            return ""
        raise AssertionError(f"Unexpected real network command request: {args}")


class IsolatedCiscoLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.original_path = recovery.CHECKPOINT
        recovery.CHECKPOINT = Path(self.tmp.name) / "checkpoint.json"
        self.addCleanup(setattr, recovery, "CHECKPOINT", self.original_path)
        self.mac = SimulatedMac()

        for item, value in [
            ("command", self.mac.command),
            ("network_service_for_device", lambda device: "Ethernet"),
            # A simulated private checkpoint is not actually root-owned.
            ("read_checkpoint", lambda: json.loads(recovery.CHECKPOINT.read_text())),
        ]:
            patcher = mock.patch.object(recovery, item, side_effect=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        root = mock.patch.object(recovery.os, "geteuid", return_value=0)
        root.start()
        self.addCleanup(root.stop)

    def test_three_connect_disconnect_cycles_restore_manual_ip_dns_and_route(self):
        for _ in range(3):
            self.assertEqual(recovery.snapshot(), BASELINE)
            self.mac.vpn_mutates_network()
            self.mac.vpn_route_ends()
            recovery.restore()
            self.assertEqual(recovery.capture(), BASELINE)
            self.assertTrue(recovery.default_route_matches(BASELINE))
            self.assertFalse(recovery.CHECKPOINT.exists())

    def test_crash_recovery_does_not_erase_checkpoint_if_vpn_route_stays(self):
        self.assertEqual(recovery.snapshot(), BASELINE)
        self.mac.vpn_mutates_network()
        with self.assertRaisesRegex(
            ValueError, "CISCO_NETWORK_DEFAULT_ROUTE_UNVERIFIED"
        ):
            recovery.restore()
        self.assertEqual(self.mac.mode, "manual")
        self.assertEqual(self.mac.dns, BASELINE["dns"])
        self.assertTrue(recovery.CHECKPOINT.exists())
        self.mac.vpn_route_ends()
        recovery.restore()
        self.assertTrue(recovery.default_route_matches(BASELINE))
        self.assertFalse(recovery.CHECKPOINT.exists())

    def test_unverified_recovery_does_not_start_a_second_session(self):
        recovery.snapshot()
        self.mac.vpn_mutates_network()
        with self.assertRaisesRegex(ValueError, "CISCO_NETWORK_CHECKPOINT_EXISTS"):
            recovery.snapshot()
        self.assertTrue(recovery.CHECKPOINT.exists())

    def test_isolation_never_invokes_subprocesses_or_real_network_commands(self):
        with mock.patch.object(recovery.subprocess, "run",
                               side_effect=AssertionError("real subprocess prohibited")):
            recovery.snapshot()
            self.mac.vpn_mutates_network()
            self.mac.vpn_route_ends()
            recovery.restore()
        self.assertFalse(recovery.CHECKPOINT.exists())


if __name__ == "__main__":
    unittest.main()
