"""Keep every required Agent feature marker across layered startup patches."""
import ast
from pathlib import Path
import shlex
import unittest

ROOT = Path(__file__).resolve().parents[1]
rollout_source = ROOT / "backend/app/unified_l3_agent_rollout_v49.py"
tree = ast.parse(rollout_source.read_text(encoding="utf-8"))
func = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_marker_probe_command")


class RolloutMarkerTests(unittest.TestCase):
    def setUp(self):
        self.ns = {
            "shlex": shlex,
            "_AGENT_MARKER": "TWINPANEL_ACTIVE_TRANSPORT_AUTHORITY_V258",
            "_AGENT_REQUIRED_MARKERS": {"TWINPANEL_SERVICE_ROUTING_FAST_SNAPSHOT_V140"},
        }
        exec(compile(ast.Module(body=[func], type_ignores=[]), str(rollout_source), "exec"), self.ns)

    def test_both_markers_required(self):
        command = self.ns["_marker_probe_command"]()
        self.assertEqual(command.count("grep -Fq"), 2)
        self.assertIn("TWINPANEL_ACTIVE_TRANSPORT_AUTHORITY_V258", command)
        self.assertIn("TWINPANEL_SERVICE_ROUTING_FAST_SNAPSHOT_V140", command)
        self.assertIn(" && ", command)

    def test_v140_is_still_required_when_newer_authority_marker_wins(self):
        self.ns["_AGENT_MARKER"] = "TWINPANEL_FUTURE_TRANSPORT_V999"
        command = self.ns["_marker_probe_command"]()
        self.assertIn("TWINPANEL_SERVICE_ROUTING_FAST_SNAPSHOT_V140", command)
        self.assertIn("TWINPANEL_FUTURE_TRANSPORT_V999", command)

    def test_installed_agent_must_be_running(self):
        cmd = self.ns["_marker_probe_command"](verify_service=True)
        self.assertIn("systemctl is-active --quiet twinpanel-agent.service", cmd)

    def test_v140_patch_registers_mandatory_marker(self):
        script = (ROOT / "backend/app/service_routing_stability_v139.py").read_text(encoding="utf-8")
        self.assertIn("rollout._AGENT_REQUIRED_MARKERS.add(AGENT_MARKER)", script)

    def test_agent_installer_uses_interpreter_pip_not_relocated_entrypoint(self):
        source = (ROOT / "backend/app/routers/provision.py").read_text(encoding="utf-8")
        self.assertIn("/opt/twinpanel-agent/venv/bin/python -m pip install", source)
        self.assertNotIn("/opt/twinpanel-agent/venv/bin/pip install", source)
        self.assertNotIn("/opt/twinpanel-agent/venv/bin/python -m pip install --upgrade pip", source)
        self.assertIn('"import httpx,psutil', source)
        self.assertIn("--timeout 15 --retries 2", source)

    def test_no_unmarked_agent_is_accepted(self):
        command = self.ns["_marker_probe_command"]()
        for marker in ("TWINPANEL_ACTIVE_TRANSPORT_AUTHORITY_V258", "TWINPANEL_SERVICE_ROUTING_FAST_SNAPSHOT_V140"):
            self.assertIn(marker, command)


if __name__ == "__main__":
    unittest.main()
