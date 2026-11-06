"""Regression: shared tunnel host is not a dedicated Xray TLS domain.

Runs without SSH/network/database and without importing runtime side effects.
"""
import ast
from pathlib import Path
from types import SimpleNamespace

root = Path(__file__).resolve().parents[1]
adaptive = (root / "app" / "xray_adaptive_three_profiles_v47.py").read_text("utf-8")
reconcile = (root / "app" / "xray_profile_reconcile_v36.py").read_text("utf-8")
migration = (root / "scripts" / "twinpanel_migration_classic_sequential_v3.py").read_text("utf-8")
jobs = (root / "app" / "services" / "node_auto_backfill_v1.py").read_text("utf-8")
runner = (root / "scripts" / "twinpanel_node_auto_backfill_v1.py").read_text("utf-8")
for name, source in (("adaptive", adaptive), ("reconcile", reconcile),
                     ("migration", migration), ("jobs", jobs), ("runner", runner)):
    compile(source, name + ".py", "exec")


def pure_function(source, name):
    tree = ast.parse(source)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    fn.decorator_list = []
    fn.returns = None
    for arg in fn.args.args:
        arg.annotation = None
    module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    env = {}
    exec(compile(module, "<pure-test>", "exec"), env)
    return env[name]


for source in (adaptive, reconcile):
    effective = pure_function(source, "_effective_domain")
    new_exit = SimpleNamespace(xray_domain=None, public_domain="tunel1.in88.sbs")
    old_exit = SimpleNamespace(xray_domain="v2ray1.in88.sbs", public_domain="tunel1.in88.sbs")
    assert effective(new_exit) == "", "shared tunnel domain must not enable TLS mode"
    assert effective(old_exit) == "v2ray1.in88.sbs"

assert 'if _required_profiles_v47(node) <= ready_profiles:' in migration
assert 'items=[' in migration and 'item if ad._autosync_item_node_id(x)==node_id else x' in migration
assert 'client_id=str(uuid.UUID(client_id))' in migration
assert 'repair_missing_v2ray_jobs(db)' in runner
assert 'db.get(NodeBackfillJobV1, (int(node_id), "v2ray"))' in jobs
assert 'or not node.enable_v2ray' in jobs
print("NODE_XRAY_MISSING_PROFILES_REGRESSION=PASS")
