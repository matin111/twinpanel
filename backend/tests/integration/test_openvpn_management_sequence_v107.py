from __future__ import annotations

import ast
import socket
import time
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[2]
RUNTIME_PATH = BACKEND / "app" / "services" / "openvpn_quota_runtime_v106.py"


def _function_source(source: str, tree: ast.AST, name: str) -> str:
    node = next(
        item
        for item in ast.walk(tree)
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == name
    )
    segment = ast.get_source_segment(source, node)
    assert segment is not None, name
    return segment


class _FakeManagementSocket:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self._responses = [
            (
                b"TITLE,OpenVPN 2.6.19\n"
                b"TIME,2026-10-20 15:06:24,1792508784\n"
                b"HEADER,CLIENT_LIST,Common Name,Real Address,Virtual Address,"
                b"Virtual IPv6 Address,Bytes Received,Bytes Sent,Connected Since,"
                b"Connected Since (time_t),Username,Client ID,Peer ID,Data Channel Cipher\n"
                b"CLIENT_LIST,mv11n5,10.253.0.21:10930,10.92.0.2,,3215,3704,"
                b"2026-10-20 15:06:22,1792508782,UNDEF,0,0,AES-256-GCM\n"
                b"END\n"
            )
        ]

    def sendall(self, payload: bytes) -> None:
        self.writes.append(payload)

    def recv(self, _size: int) -> bytes:
        if self._responses:
            return self._responses.pop(0)
        return b""


def main() -> None:
    source = RUNTIME_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert 'b"status 2\\nquit\\n"' not in source

    helper_source = _function_source(
        source,
        tree,
        "_read_openvpn_management_status",
    )

    namespace = {
        "time": time,
        "socket": socket,
    }
    exec(
        compile(
            helper_source,
            "<_read_openvpn_management_status>",
            "exec",
        ),
        namespace,
    )

    fake = _FakeManagementSocket()
    output = namespace["_read_openvpn_management_status"](fake)

    assert fake.writes == [
        b"status 2\n",
        b"quit\n",
    ], fake.writes
    assert "CLIENT_LIST,mv11n5" in output
    assert output.rstrip().endswith("END")

    remote_marker = '_REMOTE_OPENVPN_STATUS_COMMAND = r\'\'\''
    remote_start = source.index(remote_marker)
    remote_end = source.index("\n\n\ndef _int_counter", remote_start)
    remote = source[remote_start:remote_end]

    assert 'sock.sendall(b"status 2\\n")' in remote
    assert 'sock.sendall(b"quit\\n")' in remote
    assert remote.index('sock.sendall(b"status 2\\n")') < remote.index(
        'sock.sendall(b"quit\\n")'
    )
    assert 'joined = b"".join(chunks)' in remote
    assert 'joined.endswith(b"END\\n")' in remote

    print("OPENVPN_MANAGEMENT_SEQUENCE_V107_OK")


if __name__ == "__main__":
    main()
