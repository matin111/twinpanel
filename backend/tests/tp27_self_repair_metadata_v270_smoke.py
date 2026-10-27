from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "backend" / "app" / "transport_candidates" / "common.py"
TP27 = ROOT / "backend" / "app" / "tp27_self_repair_v265.py"


def _function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            segment = ast.get_source_segment(source, node)
            if not segment:
                raise AssertionError(f"source segment missing: {name}")
            return segment
    raise AssertionError(f"function not found: {name}")


def main() -> None:
    common_source = COMMON.read_text(encoding="utf-8")
    tp27_source = TP27.read_text(encoding="utf-8")

    compile(common_source, str(COMMON), "exec")
    compile(tp27_source, str(TP27), "exec")

    merge = _function_source(common_source, "merge_meta_preserving_smart_auto")

    # Candidate installers may rewrite transport-owned config_text, but they must
    # preserve controller lifecycle namespaces that remain valid across rebuilds.
    assert '"smart_auto_v21"' in merge
    assert '"tp27_self_repair_v265"' in merge
    assert "merged_state.update(explicit)" in merge

    repair_meta = _function_source(tp27_source, "_repair_meta")
    assert '"tp27_self_repair_v265"' in repair_meta
    assert '"last_repair_epoch"' in repair_meta
    assert '"last_result": "online"' in repair_meta

    print("TP27_SELF_REPAIR_METADATA_V270=PASS")


if __name__ == "__main__":
    main()
