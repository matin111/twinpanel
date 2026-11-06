"""Regression for centrally prioritized, bounded migration backfill batches."""
import ast
import re
from pathlib import Path

root=Path(__file__).resolve().parents[1]
scheduler=(root/"scripts/twinpanel_node_auto_backfill_v1.py").read_text("utf8")
runner=(root/"scripts/twinpanel_existing_node_backfill_v1.py").read_text("utf8")
policy=(root/"app/services/central_backfill_priority_v1.py").read_text("utf8")
for name,source in (("scheduler",scheduler),("runner",runner),("policy",policy)):
    compile(source,name,"exec")

tree=ast.parse(scheduler)
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="parsed_pair_count")
for arg in fn.args.args:
    arg.annotation=None
fn.returns=None
mod=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]))
env={"re":re,"ast":ast,"PAIR_LIMIT":20,"CYCLES_PER_BATCH":3}
exec(compile(mod,"parsed_pair_count","exec"),env)
parse=env["parsed_pair_count"]

def marker(value):
    return "NODE_BACKFILL_CYCLE "+repr({"new_pairs":value})+"\n"

assert parse(marker(20))==20
assert parse(marker(20)+marker(20)+marker(15))==55
assert parse(marker(20)+marker(0))==20
assert parse(marker(21)) is None
assert parse(marker(-1)) is None
assert parse(marker(20)*4) is None
assert parse("other output\n") is None
assert 'CYCLES_PER_BATCH = 3' in scheduler
assert '"--max-cycles", str(CYCLES_PER_BATCH)' in scheduler
assert 'NODE_BACKFILL_PREEMPTED_FOR_NEW_ACCOUNT' in runner
assert 'if new_account_work_has_priority():' in runner
assert 'StoreOrder.status == "provisioning"' in policy
assert 'ResellerBotOrder.status == "provisioning"' in policy
assert 'FastProvisionJobV1.state.in_(("queued", "running", "retry"))' in policy
print("CENTRAL_MIGRATED_BACKFILL_BATCH_SMOKE=PASS")
