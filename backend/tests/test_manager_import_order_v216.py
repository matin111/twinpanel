from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "app" / "tunnel_transport_manager_v12.py"


def _tree() -> ast.Module:
    return ast.parse(MANAGER.read_text(encoding="utf-8"))


def _main(tree: ast.Module) -> ast.AsyncFunctionDef:
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "main":
            return node
    raise AssertionError("tunnel_transport_manager_v12.main missing")


def _call_line(main: ast.AsyncFunctionDef, name: str) -> int:
    lines = []
    for node in ast.walk(main):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id == name:
            lines.append(node.lineno)
    assert lines, f"missing call: {name}"
    return min(lines)


def _manager_runtime_import_line(main: ast.AsyncFunctionDef) -> int:
    lines = []
    for node in ast.walk(main):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "manager_runtime_v16":
            continue
        imported = {alias.name for alias in node.names}
        if "install_manager_runtime_v16" in imported:
            lines.append(node.lineno)
    assert lines, "manager_runtime_v16 must be lazy-imported inside main"
    return min(lines)


def test_v216_manager_runtime_is_not_imported_at_module_scope() -> None:
    tree = _tree()

    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        assert node.module != "manager_runtime_v16", (
            "manager_runtime_v16 module-scope import reintroduces the V202/V209 "
            "side effect before legacy V149/V151/V165 compatibility registration"
        )


def test_v216_legacy_layers_precede_manager_runtime_and_final_policy() -> None:
    tree = _tree()
    main = _main(tree)

    v149 = _call_line(main, "apply_adaptive_multilane_v149")
    v151 = _call_line(main, "apply_adaptive_multilane_v151")
    v165 = _call_line(main, "apply_adaptive_multilane_v165")
    lazy_import = _manager_runtime_import_line(main)
    manager_runtime = _call_line(main, "install_manager_runtime_v16")
    v167 = _call_line(main, "apply_smart_candidate_install_guard_v167")
    v202 = _call_line(main, "apply_spoof_candidate_policy_v202")
    v209 = _call_line(main, "apply_kernel_transport_registry_v209")

    assert v149 < v151 < v165
    assert v165 < lazy_import <= manager_runtime
    assert manager_runtime < v167
    assert v167 < v202 < v209


def test_v216_manager_runtime_still_precedes_background_workers() -> None:
    tree = _tree()
    main = _main(tree)

    manager_runtime = _call_line(main, "install_manager_runtime_v16")

    task_lines = []
    for node in ast.walk(main):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if (
            isinstance(fn, ast.Attribute)
            and isinstance(fn.value, ast.Name)
            and fn.value.id == "asyncio"
            and fn.attr == "create_task"
        ):
            task_lines.append(node.lineno)

    assert task_lines, "manager background tasks missing"
    assert manager_runtime < min(task_lines)
