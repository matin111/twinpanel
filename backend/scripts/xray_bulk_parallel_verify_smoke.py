"""Ensure bounded concurrent verification retains user-scoped rollback guarantees."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
source=(root/"app/xray_bulk_hot_sync_pilot_v1.py").read_text("utf8")
compile(source,"xray_bulk_hot_sync_pilot_v1.py","exec")
assert "from concurrent.futures import ThreadPoolExecutor" in source
assert "max_workers=min(8, len(additions))" in source
assert "lambda client: verify(tag, client[\"email\"], client[\"id\"])" in source
assert "list(pool.map(" in source
assert "api_add(tag, port, additions)" in source
assert "attempted.extend((tag, c[\"email\"]) for c in additions)" in source
assert "api_remove(tag, email)" in source
assert "bulk rollback incomplete; manual review required" in source
assert "os.replace(stage, CONF)" in source
assert "systemctl\", \"restart" not in source
print("XRAY_BULK_PARALLEL_VERIFY_SMOKE_PASS")
