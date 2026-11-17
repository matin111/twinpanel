"""Offline tests for safe non-activating, release-hashed all-node staging."""
from pathlib import Path
import importlib.util
import tempfile

STAGER = Path(__file__).resolve().parents[1] / "scripts" / "twintunnel_stage_active_nodes_v1.py"
spec = importlib.util.spec_from_file_location("twintunnel_node_stager", STAGER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_release_hash_and_non_activation():
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for name in module.ARTIFACTS:
            (root / name).write_bytes(b"# isolated lab source\n" + b"x" * 700)
        first = module.package_manifest(root)
        assert len(first["revision"]) == 20
        assert len(first["sha256"]) == len(module.ARTIFACTS)
        assert first["active"] is False
        assert module.package_manifest(root) == first
        (root / module.ARTIFACTS[0]).write_bytes(b"# changed\n" + b"x" * 700)
        second = module.package_manifest(root)
        assert first["revision"] != second["revision"]
        assert second["active"] is False

def test_missing_files_rejected():
    with tempfile.TemporaryDirectory() as folder:
        try:
            module.package_manifest(Path(folder))
        except RuntimeError as exc:
            assert "release_artifact_missing" in str(exc)
        else:
            raise AssertionError("missing release must abort")

def test_staging_cannot_start_services():
    source = STAGER.read_text()
    assert "STAGE_BASE = \"/opt/twintunnel-staging\"" in source
    assert '"active": False' in source
    assert "production_data_plane_changed" in source
    assert "systemctl restart" not in source
    assert "systemctl enable" not in source
    assert "iptables " not in source
    assert "ip route add" not in source

if __name__ == "__main__":
    for test in (test_release_hash_and_non_activation, test_missing_files_rejected,
                 test_staging_cannot_start_services):
        test()
    print("TWINTUNNEL_NODE_STAGING_V1_SMOKE_OK")
