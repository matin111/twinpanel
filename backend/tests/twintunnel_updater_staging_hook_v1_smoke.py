"""Verify GitHub release updater schedules isolated all-node staging safely."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

UPDATER = Path(__file__).resolve().parents[1] / "scripts" / "twinpanel_public_updater_v69.py"
spec = importlib.util.spec_from_file_location("twinpanel_updater_stage_test", UPDATER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_staging_requires_complete_release():
    with tempfile.TemporaryDirectory() as tmp:
        assert module._schedule_twintunnel_node_staging_v1(Path(tmp)) is False

def test_staging_runs_detached_without_enabling_tunnels():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        script = root / "backend/scripts/twintunnel_stage_active_nodes_v1.py"
        script.parent.mkdir(parents=True)
        script.write_text("# test script")
        source = root / "ops/twintunnel-lab"
        source.mkdir(parents=True)
        for filename in ("udp_multiuser_mux.py", "udp_turkey_transit_relay.py",
                         "udp_three_path_fault_probe.py"):
            (source / filename).write_text("# test artifact")
        (root / "VERSION").write_text("1.1.0-rc.999\n")
        original_is_file = Path.is_file
        def fake_is_file(path):
            if str(path) == "/usr/bin/systemd-run":
                return True
            return original_is_file(path)
        with patch.object(Path, "is_file", fake_is_file), patch.object(
            module.subprocess, "run",
            return_value=subprocess.CompletedProcess([],0,"",""),
        ) as runner:
            assert module._schedule_twintunnel_node_staging_v1(root) is True
            args = runner.call_args.args[0]
            assert args[0] == "/usr/bin/systemd-run"
            assert "--collect" in args
            assert "--unit=twinpanel-twintunnel-stage-1.1.0-rc.999" in args
            assert "--apply" in args
            assert "--concurrency" in args
            assert "--setenv=PYTHONPATH=/opt/twinpanel/current/backend" in args
            assert "iptables" not in " ".join(args)
            assert "--restart" not in args

def test_failure_is_nonfatal():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        (root/"backend/scripts").mkdir(parents=True)
        (root/"backend/scripts/twintunnel_stage_active_nodes_v1.py").write_text("#")
        src=root/"ops/twintunnel-lab"
        src.mkdir(parents=True)
        for name in ("udp_multiuser_mux.py","udp_turkey_transit_relay.py",
                     "udp_three_path_fault_probe.py"):
            (src/name).write_text("#")
        (root/"VERSION").write_text("1.1.0-rc.999")
        old=Path.is_file
        with patch.object(Path,"is_file",lambda path: True if str(path)=="/usr/bin/systemd-run" else old(path)):
            with patch.object(module.subprocess,"run",
                              return_value=subprocess.CompletedProcess([],1,"","")):
                assert module._schedule_twintunnel_node_staging_v1(root) is False

if __name__=="__main__":
    test_staging_requires_complete_release()
    test_staging_runs_detached_without_enabling_tunnels()
    test_failure_is_nonfatal()
    print("TWINTUNNEL_UPDATER_STAGING_HOOK_V1_OK")
