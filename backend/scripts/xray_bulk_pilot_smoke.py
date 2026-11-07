"""Regression for bounded, restart-free Xray bulk hot-sync pilot."""
import ast
from pathlib import Path
import sys
from uuid import uuid4

root = Path(__file__).resolve().parents[1]
module = (root / "app/xray_bulk_hot_sync_pilot_v1.py").read_text("utf8")
runner = (root / "scripts/twinpanel_xray_bulk_pilot_v1.py").read_text("utf8")
compile(module, "xray_bulk_hot_sync_pilot_v1.py", "exec")
compile(runner, "twinpanel_xray_bulk_pilot_v1.py", "exec")
env = {"__name__": "_test_bulk"}
exec(compile(module, "<bulk>", "exec"), env)
build = env["bulk_hot_sync_script"]
ident = str(uuid4())
script = build([(ident, "mv-12345@twinpanel")])
compile(script, "<remote>", "exec")
assert "systemctl\", \"restart" not in script
assert "systemctl\", \"reload" not in script
assert '["systemctl", "is-active", "--quiet", "xray"]' in script
assert '["XRAY", "api", "adu"' not in script  # true command uses variable
assert '[XRAY, "api", "adu", API, str(path)]' in script
assert "os.replace(stage, CONF)" in script
assert "rollback incomplete" in script
assert "os.replace(stage, CONF)" in script  # remote is the sole atomic config writer
assert "centrally_published" in runner
assert "db.commit()" in runner
assert "sub.traffic_used_bytes >= sub.traffic_limit_bytes" in runner
assert "current.append(item)" in runner
assert "ad._xray(db, node, sub, user, ident," in runner
assert "if not apply or not chosen:" in runner
assert "new_account_work_has_priority()" in runner
assert "if current is not None:" in runner
assert "if len(known) != 1 or" in runner
assert "cred is None or not cred.config_text_encrypted" in runner
assert "conn.run(command, check=False)" in runner
assert "node.retired_at is not None" in runner
for entries in (
    [],
    [(ident, "mv-1@twinpanel")] * 2,
    [(ident, "mv-1@twinpanel")] * 11,
    [("not-a-uuid", "mv-1@twinpanel")],
    [(ident, "not-a-twinpanel-user")],
):
    try:
        build(entries)
    except (ValueError, TypeError):
        pass
    else:
        raise AssertionError("invalid pilot payload was accepted")
print("XRAY_BULK_PILOT_SMOKE_PASS")
