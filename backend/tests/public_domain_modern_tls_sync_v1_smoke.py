from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app import naive_tls_lifecycle_v224
from app.models import NodeType
from app.routers import account_delivery as ad


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class FakeDB:
    def __init__(self, rows):
        self.rows = rows

    def query(self, *args, **kwargs):
        return FakeQuery(self.rows)


class FakeConnection:
    def __init__(self):
        self.closed = False
        self.waited = False

    def close(self):
        self.closed = True

    async def wait_closed(self):
        self.waited = True


def test_exit_public_domain_syncs_managed_tls_once():
    node = SimpleNamespace(
        id=33,
        node_type=NodeType.EXIT,
        public_domain="tunel4.in88.sbs",
        public_ip="217.195.200.133",
    )
    rows = [
        SimpleNamespace(protocol="hysteria2"),
        SimpleNamespace(protocol="tuic"),
        SimpleNamespace(protocol="anytls"),
    ]
    db = FakeDB(rows)
    conn = FakeConnection()

    with (
        patch.object(ad, "ssh_connect_saved", new=AsyncMock(return_value=conn)) as ssh,
        patch.object(
            naive_tls_lifecycle_v224,
            "ensure_managed_naive_tls",
            new=AsyncMock(return_value={"rotated": True}),
        ) as ensure_tls,
    ):
        result = asyncio.run(ad._sync_modern_public_domain_tls(node, db))

    assert result == {
        "status": "rotated",
        "rotated": True,
        "protocols": ["anytls", "hysteria2", "tuic"],
    }
    ssh.assert_awaited_once_with(node, db)
    ensure_tls.assert_awaited_once_with(conn, node)
    assert conn.closed and conn.waited


def test_no_exit_or_no_tls_protocols_never_opens_ssh():
    iran = SimpleNamespace(id=2, node_type=NodeType.IRAN)
    with patch.object(ad, "ssh_connect_saved", new=AsyncMock()) as ssh:
        result = asyncio.run(ad._sync_modern_public_domain_tls(iran, FakeDB([])))
        assert result == {"status": "not_required", "rotated": False, "protocols": []}

        exit_without_tls = SimpleNamespace(id=7, node_type=NodeType.EXIT)
        result = asyncio.run(ad._sync_modern_public_domain_tls(exit_without_tls, FakeDB([])))
        assert result == {"status": "not_required", "rotated": False, "protocols": []}

    ssh.assert_not_awaited()


def test_tls_failure_closes_ssh_and_propagates():
    node = SimpleNamespace(id=33, node_type=NodeType.EXIT)
    conn = FakeConnection()
    with (
        patch.object(ad, "ssh_connect_saved", new=AsyncMock(return_value=conn)),
        patch.object(
            naive_tls_lifecycle_v224,
            "ensure_managed_naive_tls",
            new=AsyncMock(side_effect=RuntimeError("managed_tls_failed")),
        ),
    ):
        try:
            asyncio.run(
                ad._sync_modern_public_domain_tls(
                    node,
                    FakeDB([SimpleNamespace(protocol="hysteria2")]),
                )
            )
        except RuntimeError as exc:
            assert str(exc) == "managed_tls_failed"
        else:
            raise AssertionError("TLS failure must not be reported as success")

    assert conn.closed and conn.waited


def main() -> None:
    test_exit_public_domain_syncs_managed_tls_once()
    test_no_exit_or_no_tls_protocols_never_opens_ssh()
    test_tls_failure_closes_ssh_and_propagates()
    print("PUBLIC_DOMAIN_MODERN_TLS_SYNC_V1_SMOKE=PASS")


if __name__ == "__main__":
    main()
