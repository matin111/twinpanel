from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAIN_CUSTOM = ROOT / "backend/app/telegram_runtime_custom.py"
MAIN_RUNTIME = ROOT / "backend/app/telegram_runtime_bot.py"
RESELLER_RUNTIME = ROOT / "backend/app/reseller_bot_runtime_owned.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _function_source(path: Path, function_name: str) -> str:
    source = _source(path)
    tree = ast.parse(source, filename=str(path))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"missing function {function_name} in {path}")


def _class_source(path: Path, class_name: str) -> str:
    source = _source(path)
    tree = ast.parse(source, filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"missing class {class_name} in {path}")


def verify_main_dispatcher_guard() -> None:
    dispatcher_class = _class_source(MAIN_CUSTOM, "MembershipAwareDispatcher")
    custom_main = _function_source(MAIN_CUSTOM, "main")
    runtime_main = _function_source(MAIN_RUNTIME, "main")

    assert "AiogramDispatcher" in dispatcher_class, "membership dispatcher must derive from aiogram Dispatcher"
    assert "install_membership_guard(self)" in dispatcher_class, "membership guard must be installed on Dispatcher"
    assert "runtime.Dispatcher = MembershipAwareDispatcher" in custom_main, "main runtime must use guarded Dispatcher"
    assert "install_membership_guard(runtime.router)" not in custom_main, "router-only guard reintroduces sibling bypass"

    # The legacy main runtime intentionally mounts feature routers directly on
    # Dispatcher. Keep this assertion so CI fails if enforcement is ever moved
    # back to only runtime.router while sibling routers still exist.
    direct_dispatcher_routers = (
        "dp.include_router(purchase_router)",
        "dp.include_router(wallet_router)",
        "dp.include_router(support_router)",
    )
    assert any(item in runtime_main for item in direct_dispatcher_routers), (
        "smoke assumption changed: expected at least one main feature router "
        "to be mounted directly on Dispatcher"
    )


def verify_reseller_parent_guard() -> None:
    build_router = _function_source(RESELLER_RUNTIME, "build_router")
    guard = "install_membership_guard(parent, reseller_id=reseller_id)"
    assert guard in build_router, "reseller parent router must carry scoped membership guard"

    guard_index = build_router.index(guard)
    first_child_index = build_router.find("parent.include_router(")
    assert first_child_index != -1, "reseller parent must include child routers"
    assert guard_index < first_child_index, "reseller guard must be installed before child routers"


def main() -> None:
    verify_main_dispatcher_guard()
    verify_reseller_parent_guard()
    print("TELEGRAM_MEMBERSHIP_ENFORCEMENT_SMOKE=PASS")


if __name__ == "__main__":
    main()
