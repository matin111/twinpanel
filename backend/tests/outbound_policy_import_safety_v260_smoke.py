from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "backend" / "app" / "outbound_policy_standalone_adapters_v257.py"

spec = importlib.util.spec_from_file_location("outbound_policy_standalone_adapters_v257_import_smoke", MODULE_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

script = module.STANDALONE_RECONCILE_SCRIPT
assert "def sudoku_generator_text():" in script
assert script.count("raise SystemExit(0)") == 2
compile(script, "outbound-policy-standalone-v257", "exec")

print("OUTBOUND_POLICY_IMPORT_SAFETY_V260_OK")
