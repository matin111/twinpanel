from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TP27 = ROOT / "backend" / "app" / "transport_candidates" / "tp27_fast.py"


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
    source = TP27.read_text(encoding="utf-8")
    compile(source, str(TP27), "exec")

    existing = _function_source(source, "_existing_repair_state")
    assert 'TunnelTransport.transport == NAME' in existing
    assert 'meta.get("tp27_self_repair_v265")' in existing

    merge = _function_source(source, "_with_repair_state")
    assert 'out["tp27_self_repair_v265"]' in merge

    install = _function_source(source, "install")
    assert "repair_state = _existing_repair_state(db, tunnel_id)" in install
    assert install.count("_with_repair_state(") >= 3

    print("TP27_SELF_REPAIR_METADATA_V270=PASS")


if __name__ == "__main__":
    main()
