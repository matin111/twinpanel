"""Static contracts for the safe new-account quota batch optimization.

Integration performance and correctness are also tested against a live,
transaction-rolled-back snapshot before production rollout.
"""
from __future__ import annotations
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FILES=[
    ROOT/"backend/app/services/quota_refresh.py",
    ROOT/"backend/app/services/quota_node_sync.py",
    ROOT/"backend/app/services/accounting_device_map_batch_v1.py",
]
for f in FILES:
    ast.parse(f.read_text(encoding="utf-8"),filename=str(f))

refresh=FILES[0].read_text(encoding="utf-8")
canonical=FILES[1].read_text(encoding="utf-8")
batch=FILES[2].read_text(encoding="utf-8")

assert "build_accounting_devices_by_node(" in refresh
assert "selected_node_ids=node_ids" in refresh
assert "precomputed_devices=devices_by_node[node_id]" in refresh
assert "quota_batch_generation_failed:" in refresh
assert '"ok": False' in refresh
assert "quota_node_not_in_batched_snapshot" in refresh
assert "with db.begin_nested()" in refresh
assert "from .quota_node_sync import sync_node_config" in refresh

assert "precomputed_devices: list[dict[str, Any]] | None = None" in canonical
assert "if precomputed_devices is None else precomputed_devices" in canonical
assert "build_node_devices(db, int(node_id))" in canonical
assert '"telemetry_policy"' in canonical and '"fail_closed": True' in canonical

assert "selected_node_ids: set[int] | None = None" in batch
assert "candidate_nodes = set(node_ids)" in batch
assert "devices_by_key" in batch
assert "str(device.status or \"\").strip().lower() != \"active\"" in batch
assert "_runtime_identity(" in batch
assert "_CACHE_KEY" in batch

print("FAST_NEW_V2RAY_QUOTA_BATCH_V1_SMOKE=PASS")
