"""Safe smoke for V2Ray backfill reusable SSH ownership and wrapper plumbing."""
import ast
from pathlib import Path

root=Path(__file__).resolve().parents[1]
runtime=(root/"app/xray_modern_runtime.py").read_text("utf-8")
wrapper=(root/"app/xray_adaptive_three_profiles_v47.py").read_text("utf-8")
batch=(root/"scripts/twinpanel_migration_classic_sequential_v3.py").read_text("utf-8")
for name,source in (("runtime",runtime),("wrapper",wrapper),("batch",batch)):
    compile(source,name,"exec")

tree=ast.parse(runtime)
fn=next(x for x in tree.body if isinstance(x,ast.AsyncFunctionDef) and x.name=="_xray_account_modern")
assert any(x.arg=="reusable_connection" for x in fn.args.kwonlyargs)
assert "owns_connection = reusable_connection is None" in runtime
assert "if owns_connection:" in runtime
assert "reusable_connection if reusable_connection is not None else await account_delivery.ssh_connect_saved" in runtime
assert "reusable_connection=reusable_connection" in wrapper
assert "reusable_connection=shared_conn" in batch
assert "if shared_conn is not None and shared_conn.is_closing():" in batch
assert "shared_conn.close()" in batch and "await shared_conn.wait_closed()" in batch
assert "str(uuid.UUID(client_id))" in batch
assert "if str(item.get('uuid') or '') != client_id:" in batch
assert "global Xray restart is forbidden" in runtime
print("XRAY_SHARED_SSH_BATCH_SMOKE_PASS")
