"""Regression for partial progress, safe diagnostics and post-commit yielding."""
import ast
import re
from pathlib import Path

root=Path(__file__).resolve().parents[1]
worker=(root/"scripts/twinpanel_node_auto_backfill_v1.py").read_text("utf8")
runner=(root/"scripts/twinpanel_existing_node_backfill_v1.py").read_text("utf8")
queue=(root/"app/services/node_auto_backfill_v1.py").read_text("utf8")
for label,source in (("worker",worker),("runner",runner),("queue",queue)):
    compile(source,label+".py","exec")

fn=next(x for x in ast.parse(worker).body
        if isinstance(x,ast.FunctionDef) and x.name=="sanitized_backfill_error")
for arg in fn.args.args:
    arg.annotation=None
fn.returns=None
env={"re":re,"ast":ast}
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),"<diag>","exec"),env)
parse=env["sanitized_backfill_error"]
assert parse("NODE_BACKFILL_SAFETY_STOP {'node_id': 13, 'error_type': 'RuntimeError'}\n",4)=="BACKFILL_SAFETY_RuntimeError"
assert parse("NODE_BACKFILL_SAFETY_STOP {'error_type': 'ValueError'}\n",4)=="BACKFILL_SAFETY_ValueError"
assert parse("NODE_BACKFILL_SAFETY_STOP {'error_type': 'Password=SECRET'}\n",4)=="BACKFILL_EXIT_4"
assert parse("random output with tokens\n",4)=="BACKFILL_EXIT_4"

assert "sanitized_backfill_error(proc.stdout or \"\", proc.returncode)" in worker
assert "NODE_BACKFILL_YIELD_AFTER_PROGRESS" in runner
assert "if count:" in queue and "row.completed_pairs = int(row.completed_pairs or 0) + count" in queue
assert "row.error_code = str(error_code)[:96]" in queue
print("BACKFILL_SAFE_PROGRESS_REGRESSION_PASS")
