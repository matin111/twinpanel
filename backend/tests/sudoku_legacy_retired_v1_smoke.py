"""No retired Sudoku per-subscription service may be recreated after cutover."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import standalone_subscription_accounts as legacy
from app.central_sudoku_bulk_runtime_v1 import apply_bulk
from app.services.sudoku_central_delivery_v1 import prefer_central_sudoku_items
from scripts.twinpanel_central_sudoku_node_bulk_v1 import stage


async def expect_exception(awaitable, expected: str):
    try:
        await awaitable
    except Exception as exc:
        assert expected in str(exc), (type(exc).__name__, str(exc))
    else:
        raise AssertionError("retired Sudoku creator accepted write")


def test_all_old_user_install_paths_fail_before_network_or_db():
    secret=SimpleNamespace(protocol="sudoku")
    asyncio.run(expect_exception(
        legacy.apply_account(None, None, secret, 18553),
        "SUDOKU_PER_USER_SERVICE_RETIRED_USE_SHARED_CENTRAL_NODE",
    ))
    asyncio.run(expect_exception(
        legacy._apply_sudoku(None, None, secret, 18553),
        "SUDOKU_PER_USER_SERVICE_RETIRED_USE_SHARED_CENTRAL_NODE",
    ))
    asyncio.run(expect_exception(
        apply_bulk(None, []),
        "SUDOKU_LEGACY_BULK_DISABLED_USE_SHARED_V2",
    ))
    asyncio.run(expect_exception(
        stage(19, 3000, True),
        "SUDOKU_LEGACY_STAGE_RETIRED_USE_SHARED_V2",
    ))


def test_other_standalone_protocol_paths_unchanged():
    from app import standalone_subscription_accounts as accounts
    src=Path(accounts.__file__).read_text(encoding="utf-8")
    assert 'if secret.protocol == "mieru":' in src
    assert 'if secret.protocol == "trusttunnel":' in src
    assert 'if secret.protocol == "amneziawg":' in src
    assert "async def _remove_sudoku(" in src


def test_central_only_feed_never_returns_dead_legacy_items():
    class FakeDB:
        def get(self, obj, node_id):
            return None
    old=[{"node_id":6,"port":30000,"uri":"sudoku://old"}]
    assert prefer_central_sudoku_items(FakeDB(),old) == []


def test_route_builder_never_generates_old_nat_ports():
    from app import modern_protocol_tunnel_binding_v251 as route
    config = route._configured_modern_protocols
    shared = route._sudoku_shared_exit
    mapping = route._sudoku_public_port_map
    try:
        route._configured_modern_protocols=lambda db,n:{
            "sudoku":SimpleNamespace(status="online")
        }
        route._sudoku_shared_exit=lambda db,n:False
        route._sudoku_public_port_map=lambda db: (_ for _ in ()).throw(
            AssertionError("old route allocation called")
        )
        node=SimpleNamespace(id=6,node_type=route.NodeType.EXIT,
                             show_to_users=True,retired_at=None)
        assert route._modern_routes_for_exit(None,node,"10.253.0.6")==[]
    finally:
        route._configured_modern_protocols=config
        route._sudoku_shared_exit=shared
        route._sudoku_public_port_map=mapping


def run():
    for name,fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("SUDOKU_LEGACY_RETIRED_V1_SMOKE_OK")


if __name__=="__main__":
    run()
