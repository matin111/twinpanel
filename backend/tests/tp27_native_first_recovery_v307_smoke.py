from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
REPAIR = ROOT / "backend/app/tp27_self_repair_v265.py"
QUARANTINE = ROOT / "backend/app/tp27_fou_quarantine_v303.py"


def _isolated_function(path: Path, name: str, variables: dict):
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    tree = ast.parse(source)
    function = next(
        item for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == name
    )
    isolated = ast.Module(body=[function], type_ignores=[])
    namespace = dict(variables)
    exec(compile(isolated, str(path), "exec"), namespace)
    return namespace[name]


def main() -> None:
    ports = (443, 8443, 2053, 2083, 10443)
    base = _isolated_function(
        REPAIR,
        "_attempt_order",
        {"tp27_fast": SimpleNamespace(FOU_PORT_CANDIDATES=ports)},
    )
    expected_fou = [("gre-fou", port) for port in ports]
    native = ("gre-native", None)

    assert base({}) == [native, *expected_fou]
    assert base({"selected_profile": "gre-native"}) == [native, *expected_fou]
    assert base({"selected_profile": "gre-fou", "fou_port": 2053}) == [
        native,
        ("gre-fou", 443),
        ("gre-fou", 8443),
        ("gre-fou", 2083),
        ("gre-fou", 10443),
        ("gre-fou", 2053),
    ]

    quarantine = _isolated_function(
        QUARANTINE,
        "_attempt_order",
        {
            "_original_attempt_order": base,
            "_active_failures": lambda cfg: dict(cfg.get("failed", {})),
            "_port": lambda value: int(value or 0),
        },
    )
    assert quarantine({"selected_profile": "gre-native"}) == [native, *expected_fou]

    # Previously, a remembered FoU failure silently moved native GRE to the
    # last position even though V265 itself offered native first.
    cfg = {
        "selected_profile": "gre-fou",
        "fou_port": 2053,
        "failed": {443: 123.0},
    }
    assert quarantine(cfg) == [
        native,
        ("gre-fou", 8443),
        ("gre-fou", 2083),
        ("gre-fou", 10443),
        ("gre-fou", 443),
        ("gre-fou", 2053),
    ]
    # Quarantine is soft: no FoU recovery option is ever discarded.
    assert set(quarantine(cfg)) == {native, *expected_fou}
    print("TP27_NATIVE_FIRST_RECOVERY_V307=PASS")


if __name__ == "__main__":
    main()
