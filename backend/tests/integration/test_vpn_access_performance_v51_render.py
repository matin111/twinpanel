from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]
SOURCE_PATH = BACKEND / "app" / "vpn_access_performance_v51.py"


def _load_renderer():
    source = SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(SOURCE_PATH))

    wanted = {
        "ACCESS_MTU",
        "ACCESS_TCP_MSS",
        "_PROTOCOL_SUBNETS",
    }
    body = []

    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {
                target.id
                for target in node.targets
                if isinstance(target, ast.Name)
            }
            if names & wanted:
                body.append(node)
        elif (
            isinstance(node, ast.FunctionDef)
            and node.name == "_performance_script"
        ):
            body.append(node)

    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)

    namespace: dict[str, object] = {}
    exec(
        compile(module, str(SOURCE_PATH), "exec"),
        namespace,
        namespace,
    )

    return namespace["_performance_script"]


def main() -> None:
    renderer = _load_renderer()
    rendered = renderer()

    assert "ACCESS_MTU=1200" in rendered
    assert "ACCESS_MSS=1160" in rendered
    assert "TWINPANEL_VPN_ACCESS_PERFORMANCE_RENDER_V89" not in rendered

    match = re.search(
        r"python3 - <<'PY_REMOTE'\n(.*?)\nPY_REMOTE(?:\n|$)",
        rendered,
        flags=re.DOTALL,
    )
    assert match is not None, "embedded PY_REMOTE heredoc not found"

    remote_python = match.group(1)

    # This is the production regression: before V89 the controller-side
    # outer f-string consumed the inner \n escapes and rendered a broken
    # multi-line string literal at <stdin>:16 on every reconciliation pass.
    compile(remote_python, "<v51-remote>", "exec")

    assert 'updated = text.rstrip() + chr(10) + line + chr(10)' in remote_python
    assert 'f"mtu = 1200"' in remote_python
    assert 'f"tun-mtu 1200"' in remote_python
    assert 'f"mssfix {ACCESS_MSS}"' in remote_python
    assert 'f"MTU = 1200"' in remote_python
    assert 'f"mtu 1200"' in remote_python
    assert 'f"mru 1200"' in remote_python

    bash = subprocess.run(
        ["bash", "-n"],
        input=rendered,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert bash.returncode == 0, bash.stdout

    print("VPN_ACCESS_PERFORMANCE_V51_RENDER_V89_OK")


if __name__ == "__main__":
    main()
