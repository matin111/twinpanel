#!/usr/bin/env python3
from __future__ import annotations

import ast
import asyncio
import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FILES = {
    "connection": ROOT / "backend/app/node_runtime_connection.py",
    "classic": ROOT / "backend/app/routers/classic_protocol_admin_v1.py",
    "modern": ROOT / "backend/app/routers/modern_protocol_admin_v2.py",
    "client": ROOT / "lib/legacy-admin-api.ts",
}


for name in ("connection", "classic", "modern"):
    path = FILES[name]
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(path))
    compile(source, str(path), "exec")

connection = FILES["connection"].read_text(encoding="utf-8")
classic = FILES["classic"].read_text(encoding="utf-8")
modern = FILES["modern"].read_text(encoding="utf-8")
client = FILES["client"].read_text(encoding="utf-8")

assert 'Node.agent_url == "local://core"' in connection
assert "class LocalRuntimeConnection" in connection
assert "asyncio.create_subprocess_shell" in connection
assert "os.geteuid() != 0" in connection
assert "start_new_session=True" in connection
assert "timeout: float | None = None" in connection
assert "asyncio.shield(communicate_task)" in connection
assert "signal.SIGTERM" in connection
assert "signal.SIGKILL" in connection
assert "exit_status = 124" in connection
assert "local command timed out after" in connection
assert "return await ssh_connect_saved(node, db)" in connection

assert "protocol_runtime_node_clause()" in classic
assert "connect_protocol_runtime(node, db)" in classic
assert '@router.post("/classic-protocol-health")' in classic
assert '@router.post("/classic-restart-protocol")' in classic
assert "ssh_connect_saved" not in classic
assert "_LOCAL_CORE_CISCO_PORT = 4443" in classic
assert "_default_port_for_node(node, protocol)" in classic
assert "is_local_core(node)" in classic

assert "protocol_runtime_node_clause()" in modern
assert "connect_protocol_runtime(node, db)" in modern
assert "def _protocol_node" in modern
assert "ssh_connect_saved" not in modern
assert "node.agent_url == \"local://core\"" not in modern

assert '"/v1/provision/classic-protocol-health"' in client
assert '"/v1/provision/classic-restart-protocol"' in client
assert '"/v1/provision/protocol-health"' not in client
assert '"/v1/provision/restart-protocol"' not in client


def load_local_runner():
    tree = ast.parse(connection, filename=str(FILES["connection"]))
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name in {"LocalRunResult", "LocalRuntimeConnection"}
    ]
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "asyncio": asyncio,
        "os": os,
        "signal": signal,
        "dataclass": dataclass,
    }
    exec(compile(module, str(FILES["connection"]), "exec"), namespace)
    return namespace["LocalRuntimeConnection"]


async def verify_local_runner_timeout() -> None:
    runner_cls = load_local_runner()
    runner = runner_cls()

    normal = await runner.run("printf 'runtime-ok'", check=False, timeout=2)
    assert normal.exit_status == 0, normal
    assert normal.stdout == "runtime-ok", normal

    started = time.monotonic()
    timed = await runner.run("sleep 10", check=False, timeout=0.15)
    elapsed = time.monotonic() - started
    assert timed.exit_status == 124, timed
    assert "timed out" in timed.stderr.lower(), timed
    assert elapsed < 3.0, elapsed

    try:
        await runner.run("sleep 10", check=True, timeout=0.15)
    except RuntimeError as exc:
        assert "timed out" in str(exc).lower(), exc
    else:
        raise AssertionError("check=True timeout must raise RuntimeError")


asyncio.run(verify_local_runner_timeout())

print("LOCAL_CORE_PROTOCOL_RUNTIME_V1_SMOKE_OK")
