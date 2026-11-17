"""Safe A/B script smoke tests — no tunnel or network access."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "compare_carriers.py"
spec = importlib.util.spec_from_file_location("twintunnel_compare_carriers", SCRIPT)
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)


class CarrierComparisonTests(unittest.TestCase):
    def test_gre_measure_preserves_short_id_and_output_label(self):
        response = '{"brand":"TwinTunnel","carrier":"Shabdiz-GRE","loss_pct":1.25,"echoed_mbps_at_test_rate":1.97,"rtt_avg_ms":105.1}'
        with patch.object(compare.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=response, stderr="")) as run:
            row = compare.measure("GRE", 2, 4, 900)
            cmd = run.call_args.args[0]
        self.assertEqual(row["carrier_id"], "GRE")
        self.assertEqual(row["carrier"], "Shabdiz-GRE")
        self.assertEqual(row["target_mbps"], 2)
        self.assertEqual(cmd[cmd.index("--host")+1], "127.0.0.1")
        self.assertEqual(cmd[cmd.index("--port")+1], "37921")
        self.assertEqual(cmd[cmd.index("--rate-mbps")+1], "2")

    def test_udp_only_local_forward_uses_correct_port(self):
        response = '{"brand":"TwinTunnel","carrier":"Shabdiz-UDP","loss_pct":0,"echoed_mbps_at_test_rate":1.99,"rtt_avg_ms":90}'
        with patch.object(compare.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=response, stderr="")) as run:
            row = compare.measure("UDP", 2, 4, 900)
            cmd = run.call_args.args[0]
        self.assertEqual(row["carrier_id"], "UDP")
        self.assertEqual(cmd[cmd.index("--port")+1], "37933")
        self.assertEqual(cmd[cmd.index("--carrier")+1], "Shabdiz-UDP")

    def test_failed_probe_never_claims_success(self):
        with patch.object(compare.subprocess, "run", return_value=SimpleNamespace(returncode=2, stdout="", stderr="no echo")):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                compare.measure("TCP", 5, 4, 900)


if __name__ == "__main__":
    unittest.main()
