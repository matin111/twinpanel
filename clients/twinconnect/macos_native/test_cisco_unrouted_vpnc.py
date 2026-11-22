"""Unit regression tests for unrouted Cisco setup. Never touch real devices."""
import importlib.util
from pathlib import Path
from subprocess import CompletedProcess
from unittest import TestCase, main
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "cisco_unrouted_vpnc", Path(__file__).with_name("cisco_unrouted_vpnc.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CiscoUnroutedTests(TestCase):
    def test_only_utun_ipv4_can_be_configured(self):
        env = {"reason": "connect", "TUNDEV": "utun4",
               "INTERNAL_IP4_ADDRESS": "10.20.30.4", "INTERNAL_IP4_MTU": "1300"}
        with patch.object(module.subprocess, "run",
                          return_value=CompletedProcess([], 0, b"", b"")) as run:
            self.assertEqual(module.execute(env), "CISCO_UTUN_CONFIGURED_UNROUTED")
            run.assert_called_once_with(
                ["/sbin/ifconfig", "utun4", "inet", "10.20.30.4",
                 "10.20.30.4", "netmask", "255.255.255.255",
                 "mtu", "1300", "up"],
                capture_output=True, timeout=8, check=False)

    def test_pre_init_and_disconnect_never_change_network(self):
        for reason in ("pre-init", "disconnect", "attempt-reconnect"):
            with self.subTest(reason=reason), patch.object(
                    module.subprocess, "run") as command:
                self.assertEqual(module.execute({"reason": reason}),
                                 "CISCO_UTUN_NO_SYSTEM_ROUTES")
                command.assert_not_called()

    def test_rejects_any_physical_or_attacker_interface(self):
        for interface in ("en0", "lo0", "utun4; route delete default",
                          "utun-4", "utun9999", "tun0"):
            env = {"reason": "connect", "TUNDEV": interface,
                   "INTERNAL_IP4_ADDRESS": "10.20.30.4"}
            with self.subTest(interface=interface), patch.object(
                    module.subprocess, "run") as command:
                with self.assertRaisesRegex(ValueError,
                                            "CISCO_TUN_INTERFACE_INVALID"):
                    module.execute(env)
                command.assert_not_called()

    def test_bad_ipv4_and_mtu_refused(self):
        good = {"reason": "connect", "TUNDEV": "utun4",
                "INTERNAL_IP4_ADDRESS": "10.20.30.4",
                "INTERNAL_IP4_MTU": "1300"}
        for bad in ({"INTERNAL_IP4_ADDRESS": "127.0.0.1"},
                    {"INTERNAL_IP4_ADDRESS": "foo"},
                    {"INTERNAL_IP4_MTU": "99999"}):
            env = {**good, **bad}
            with self.subTest(bad=bad), patch.object(
                    module.subprocess, "run") as command:
                with self.assertRaises(ValueError):
                    module.execute(env)
                command.assert_not_called()


if __name__ == "__main__":
    main()
