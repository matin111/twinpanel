"""Regression: isolated V2Ray workers must not fall back to legacy Xray."""
from pathlib import Path
import ast
root=Path(__file__).resolve().parents[1]
helper=(root/"app/xray_standalone_worker_runtime_v1.py").read_text("utf8")
batch=(root/"scripts/twinpanel_migration_classic_sequential_v3.py").read_text("utf8")
pilot=(root/"scripts/twinpanel_xray_bulk_pilot_v1.py").read_text("utf8")
for name,body in (("helper",helper),("batch",batch),("pilot",pilot)):
    compile(body,name+".py","exec")
assert "apply_xray_modern_runtime()" in helper
assert "apply_xray_adaptive_three_profiles_v47()" in helper
assert "apply_xray_hot_client_sync_v1()" in helper
assert 'worker.__module__ != "app.xray_adaptive_three_profiles_v47"' in helper
assert "activate_standalone_xray_worker()" in batch
assert 'if PROTOCOL == "v2ray":' in batch
assert "activate_standalone_xray_worker()" in pilot
assert "reusable_connection=shared_conn" in batch
assert "reusable_connection=conn" in pilot
print("XRAY_STANDALONE_WORKER_COMPOSITION_SMOKE_PASS")
