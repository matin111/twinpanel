from __future__ import annotations

import ast
from pathlib import Path


SOURCE_PATH = Path(__file__).with_name("vpn_access_performance_v51.py")


def render_v51_performance_script() -> str:
    """Render V51's remote shell without importing the full TwinPanel app.

    This intentionally compiles only the constants/function required by
    _performance_script(). It is used by CI to catch outer-f-string runtime
    errors (for example an unescaped remote variable such as ACCESS_MSS) that
    normal py_compile cannot detect.
    """

    source = SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(SOURCE_PATH))

    wanted_assignments = {
        "ACCESS_MTU",
        "ACCESS_TCP_MSS",
        "_PROTOCOL_SUBNETS",
    }
    body: list[ast.stmt] = []

    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {
                target.id
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            if names & wanted_assignments:
                body.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "_performance_script":
                body.append(node)

    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict[str, object] = {}
    exec(compile(module, str(SOURCE_PATH), "exec"), namespace, namespace)

    renderer = namespace.get("_performance_script")
    if not callable(renderer):
        raise RuntimeError("v51_performance_script_renderer_missing")

    rendered = renderer()
    if not isinstance(rendered, str) or not rendered.strip():
        raise RuntimeError("v51_performance_script_render_empty")

    return rendered


def validate_v51_performance_script() -> str:
    rendered = render_v51_performance_script()

    required = (
        "ACCESS_MTU=1200",
        "ACCESS_MSS=1160",
        'f"mssfix {ACCESS_MSS}"',
        "V51_OK=1",
        "TP_ACCESS_PERF",
    )
    missing = [token for token in required if token not in rendered]
    if missing:
        raise RuntimeError(
            "v51_performance_script_contract_missing:" + ",".join(missing)
        )

    return rendered


if __name__ == "__main__":
    validate_v51_performance_script()
    print("VPN_ACCESS_PERFORMANCE_V51_RUNTIME_RENDER=PASS")
