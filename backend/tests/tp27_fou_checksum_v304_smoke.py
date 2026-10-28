from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TP27 = ROOT / "backend" / "app" / "transport_candidates" / "tp27_fast.py"


def _literal_assignment(source: str, name: str):
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id == name:
                    if node.value is None:
                        raise AssertionError(f"assignment has no value: {name}")
                    return ast.literal_eval(node.value)
    raise AssertionError(f"assignment not found: {name}")


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

    assert _literal_assignment(source, "FOU_UDP_CHECKSUM") is True

    install_peer = _function_source(source, "_install_peer")
    assert "encap fou encap-sport auto" in install_peer
    assert "encap-dport {port} encap-csum" in install_peer
    assert "noencap-csum" not in install_peer

    install = _function_source(source, "install")
    assert '"fou_udp_checksum": "enabled"' in install

    print("TP27_FOU_CHECKSUM_V304=PASS")


if __name__ == "__main__":
    main()
