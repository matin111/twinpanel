from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.models import NodeType
from app import node_bootstrap_control_v74 as v74


ROOT = Path(__file__).resolve().parents[1]


class _IranConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    async def wait_closed(self):
        return None


class _NativeFallback:
    calls: list[dict] = []

    @classmethod
    async def open_with_private_key(
        cls,
        iran_conn,
        *,
        host: str,
        port: int,
        username: str,
        private_key: str,
    ):
        cls.calls.append(
            {
                "iran_conn": iran_conn,
                "host": host,
                "port": port,
                "username": username,
                "private_key": private_key,
            }
        )
        return "native-fallback"


async def _exercise_runtime() -> None:
    exit_node = SimpleNamespace(
        id=5,
        node_type=NodeType.EXIT,
        public_ip="203.0.113.5",
    )
    iran_node = SimpleNamespace(
        id=2,
        node_type=NodeType.IRAN,
        public_ip="198.51.100.2",
    )

    old_direct = v74._direct_saved_connect
    old_access = v74.v63._access
    old_first_iran = v74.v72._first_management_iran
    old_native = v74.v72.NativeIranExitConnection

    try:
        # Healthy direct management must perform exactly one connector call and
        # return immediately. No V61 relay candidate is allowed to participate.
        calls: list[int] = []

        async def direct_ok(node, _db):
            calls.append(int(node.id))
            return "direct-ok"

        v74._direct_saved_connect = direct_ok
        result = await v74.ssh_connect_saved_v74(exit_node, object())
        assert result == "direct-ok"
        assert calls == [5]

        # When direct Exit SSH fails, V74 must open exactly one Iran management
        # connection using the same direct primitive and then delegate to the
        # hardened V72/V73 native transport. No local ProxyCommand race exists.
        with TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "exit.key"
            key_path.write_text("TEST-PRIVATE-KEY", encoding="utf-8")
            access = SimpleNamespace(
                private_key_path=str(key_path),
                ssh_port=22,
                ssh_username="root",
            )
            iran_conn = _IranConnection()
            fallback_calls: list[int] = []

            async def direct_then_iran(node, _db):
                fallback_calls.append(int(node.id))
                if int(node.id) == 5:
                    raise RuntimeError("direct_exit_unreachable")
                assert int(node.id) == 2
                return iran_conn

            v74._direct_saved_connect = direct_then_iran
            v74.v63._access = lambda _db, _node_id: access
            v74.v72._first_management_iran = lambda _db, _node: iran_node
            v74.v72.NativeIranExitConnection = _NativeFallback
            _NativeFallback.calls.clear()

            result = await v74.ssh_connect_saved_v74(exit_node, object())
            assert result == "native-fallback"
            assert fallback_calls == [5, 2]
            assert len(_NativeFallback.calls) == 1
            native = _NativeFallback.calls[0]
            assert native["iran_conn"] is iran_conn
            assert native["host"] == "203.0.113.5"
            assert native["port"] == 22
            assert native["username"] == "root"
            assert native["private_key"] == "TEST-PRIVATE-KEY"
            assert iran_conn.closed is False

    finally:
        v74._direct_saved_connect = old_direct
        v74.v63._access = old_access
        v74.v72._first_management_iran = old_first_iran
        v74.v72.NativeIranExitConnection = old_native


def _source_guards() -> None:
    source = (ROOT / "app" / "node_bootstrap_control_v74.py").read_text(
        encoding="utf-8"
    )
    routers = (ROOT / "app" / "routers" / "__init__.py").read_text(
        encoding="utf-8"
    )

    assert "async def _direct_saved_connect" in source
    assert "asyncssh.connect(" in source
    assert "_DIRECT_TIMEOUT_SECONDS = 12" in source
    assert "provision.ssh_connect_saved = ssh_connect_saved_v74" in source
    assert "provision.ssh_connect =" not in source
    assert "from . import ssh_management_fallback_v61" not in source

    # Guard executable fanout machinery rather than prose comments which
    # deliberately document the production `ssh -> Iran -> nc` root cause.
    for forbidden in (
        "_relay_candidates(",
        "_race_connections(",
        "proxy_command=",
        "ServerAliveCountMax=1",
        "asyncio.create_subprocess_exec(\"ssh\"",
        "asyncio.create_subprocess_shell(\"ssh ",
    ):
        assert forbidden not in source, forbidden

    order = [
        "ssh_management_fallback_v61",
        "node_bootstrap_control_v72",
        "node_bootstrap_control_v73",
        "node_bootstrap_control_v74",
    ]
    positions = [routers.index(item) for item in order]
    assert positions == sorted(positions)


async def main() -> None:
    _source_guards()
    await _exercise_runtime()
    print("V74_DIRECT_BOUNDED_ASYNCSSH=PASS")
    print("V74_DIRECT_SINGLE_ATTEMPT=PASS")
    print("V74_NATIVE_IRAN_SEQUENTIAL_FALLBACK=PASS")
    print("V74_NO_LOCAL_PROXY_FANOUT=PASS")
    print("V74_IMPORT_ORDER=PASS")


if __name__ == "__main__":
    asyncio.run(main())
