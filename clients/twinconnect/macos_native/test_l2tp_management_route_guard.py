"""Offline guard tests: never modify macOS route, DNS or VPN in this suite."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "l2tp_guard", Path(__file__).with_name("l2tp_management_route_guard.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def response(value="", code=0):
    return subprocess.CompletedProcess([], code, value, "")


class L2TPGuardTests(unittest.TestCase):
    def test_reject_private_endpoint_before_any_network_operations(self):
        with patch.object(guard, "preflight") as preflight:
            self.assertEqual(guard.arm("127.0.0.1"), "L2TP_ENDPOINT_NOT_PUBLIC")
            preflight.assert_not_called()

    def test_refuses_to_arm_while_cisco_state_exists(self):
        with patch.object(guard, "PROTECT_VPNS") as paths:
            paths.__iter__.return_value = [Path("/any")]
            with patch.object(Path, "exists", return_value=True), \
                 patch.object(guard, "run") as call:
                self.assertEqual(guard.preflight()[0], "L2TP_OTHER_SYSTEM_VPN_ACTIVE")
                call.assert_not_called()

    def test_both_probes_required_before_enabling_full_route(self):
        state = {
            "mode": "armed", "interface": "en0", "verified_probes": ["1.1.1.1"],
        }
        with patch.object(guard, "verified_state", return_value=state), \
             patch.object(guard, "native_status",
                          return_value="L2TP_NATIVE_LINK_CONNECTED_UNROUTED"), \
             patch.object(guard, "ppp_interface", return_value="ppp0"), \
             patch.object(guard, "run") as cmd:
            self.assertEqual(guard.activate("ppp0"),
                             "L2TP_TWO_EGRESS_PROBES_REQUIRED")
            cmd.assert_not_called()

    def test_two_probes_must_use_independent_networks(self):
        state={"mode":"armed","interface":"en0","verified_probes":["1.1.1.1","1.0.0.1"]}
        with patch.object(guard,"verified_state",return_value=state), \
             patch.object(guard,"native_status",return_value="L2TP_NATIVE_LINK_CONNECTED_UNROUTED"), \
             patch.object(guard,"ppp_interface",return_value="ppp0"), \
             patch.object(guard,"run") as calls:
            self.assertEqual(guard.activate("ppp0"),"L2TP_TWO_EGRESS_PROBES_REQUIRED")
            calls.assert_not_called()

    def test_never_probe_arbitrary_destination(self):
        with patch.object(guard, "verified_state") as state:
            self.assertEqual(guard.probe_host("ppp0", "9.9.9.9"),
                             "L2TP_PROBE_INVALID")
            state.assert_not_called()

    def test_does_not_use_existing_admin_route(self):
        state = {"mode": "armed", "interface": "en0"}
        with patch.object(guard, "verified_state", return_value=state), \
             patch.object(guard, "native_status",
                          return_value="L2TP_NATIVE_LINK_CONNECTED_UNROUTED"), \
             patch.object(guard, "ppp_interface", return_value="ppp0"), \
             patch.object(guard, "probe_route_entries", return_value={"en0"}), \
             patch.object(guard, "route", return_value={"interface":"en0"}):
            self.assertEqual(guard.probe_host("ppp0", "1.1.1.1"),
                             "L2TP_PROBE_ROUTE_PREEXISTS")

    def test_ignore_only_physical_scoped_kernel_clones(self):
        table=("1.1.1.1 2.3.4.5 UGHWI en0\n"
               "1.1.1.1 2.3.4.5 UGHS en0\n"
               "1.1.1.1 link#18 UH ppp0\n")
        with patch.object(guard,"run",return_value=response(table)):
            self.assertEqual(guard.probe_route_entries("1.1.1.1","en0"),{"en0","ppp0"})
        with patch.object(guard,"run",return_value=response(table.splitlines()[0])):
            self.assertEqual(guard.probe_route_entries("1.1.1.1","en0"),set())

    def test_native_ppp_probe_is_not_owned_or_deleted(self):
        state={"mode":"armed","interface":"en0"}
        with patch.object(guard,"verified_state",return_value=state), \
             patch.object(guard,"native_status",return_value="L2TP_NATIVE_LINK_CONNECTED_UNROUTED"), \
             patch.object(guard,"ppp_interface",return_value="ppp0"), \
             patch.object(guard,"probe_route_entries",return_value={"ppp0"}), \
             patch.object(guard,"route",return_value={"interface":"ppp0"}), \
             patch.object(guard,"store"), patch.object(guard,"run") as calls:
            self.assertEqual(guard.probe_host("ppp0","1.1.1.1"),"L2TP_PROBE_HOST_ACTIVE")
            self.assertFalse(state["probe_owned"])
            with patch.object(guard,"load",return_value=state):
                self.assertEqual(guard.rollback_probe(),"L2TP_PROBE_ROLLBACK_VERIFIED")
            calls.assert_not_called()

    def test_connected_status_requires_live_guard_and_ppp(self):
        with patch.object(guard, "load", return_value={"mode": "leased"}), \
             patch.object(guard, "verified_state", return_value=None), \
             patch.object(guard, "native_status") as native:
            self.assertNotEqual(guard.status(), "L2TP_SYSTEM_IPV4_CONNECTED")
            native.assert_not_called()

    def test_if_state_absent_stop_does_not_stop_other_vpn(self):
        with patch.object(guard, "load", return_value={}), \
             patch.object(guard, "run") as calls:
            self.assertEqual(guard.stop(), "L2TP_SYSTEM_DISCONNECTED")
            calls.assert_not_called()

    def test_probe_must_be_verifiably_on_ppp(self):
        state = {"mode": "probing", "probe_destination": "1.1.1.1",
                 "full_interface": "ppp0"}
        with patch.object(guard, "verified_state", return_value=state), \
             patch.object(guard, "route", return_value={"interface": "en0"}), \
             patch.object(guard, "run") as calls:
            self.assertEqual(guard.verify_probe(), "L2TP_PROBE_ROUTE_MISSING")
            calls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
