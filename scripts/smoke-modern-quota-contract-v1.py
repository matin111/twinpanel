from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "backend/app/quota_schemas.py"
SYNC = ROOT / "backend/app/services/quota_node_sync.py"
MODERN = {"hysteria2", "tuic", "anytls"}


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def literal_assignment(module: ast.Module, name: str):
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"assignment not found: {name}")


def protocol_literal_values(module: ast.Module) -> set[str]:
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "ProtocolName" for target in node.targets):
            continue
        value = node.value
        if not isinstance(value, ast.Subscript) or not isinstance(value.slice, ast.Tuple):
            raise AssertionError("ProtocolName must remain an explicit Literal")
        return {
            str(item.value)
            for item in value.slice.elts
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        }
    raise AssertionError("ProtocolName not found")


def main() -> None:
    schema_tree = parse(SCHEMAS)
    sync_tree = parse(SYNC)

    protocol_names = protocol_literal_values(schema_tree)
    missing_schema = MODERN - protocol_names
    assert not missing_schema, f"modern quota schema missing: {sorted(missing_schema)}"

    mapping = literal_assignment(sync_tree, "_PROTOCOL_TO_QUOTA")
    for protocol in sorted(MODERN):
        assert mapping.get(protocol) == protocol, f"node quota mapping missing: {protocol}"

    sync_text = SYNC.read_text(encoding="utf-8")
    assert '"version": 4' in sync_text, "quota node config schema was not bumped to v4"
    assert '"fail_closed": True' in sync_text, "modern telemetry must fail closed"
    assert "synthetic zero-usage" in sync_text, "fail-closed rationale must remain explicit"

    print("MODERN_QUOTA_CONTRACT_V1_OK")
    print("protocols=", ",".join(sorted(MODERN)))


if __name__ == "__main__":
    main()
