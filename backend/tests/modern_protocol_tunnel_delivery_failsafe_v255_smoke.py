from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app import modern_protocol_tunnel_binding_v251 as binding
from app import modern_protocol_tunnel_delivery_failsafe_v255 as failsafe
from app import protocol_dataplane_desired_state_v87 as protocol_v87


MODERN = {
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
    "mieru",
    "trusttunnel",
    "amneziawg",
    "sudoku",
}

LEGACY = {
    "cisco",
    "openvpn",
    "wireguard",
    "l2tp",
    "v2ray",
}


def _state(
    node_id: int,
    *,
    transport: str = "kernel_vxlan",
    endpoint: bool = True,
    tunnel: bool = True,
    updated_at: datetime,
):
    return SimpleNamespace(
        node_id=node_id,
        selected_transport=transport,
        endpoint_reachable=endpoint,
        tunnel_reachable=tunnel,
        updated_at=updated_at,
    )


def test_two_peer_gate_is_fail_closed() -> None:
    now = datetime.now(timezone.utc)
    epoch = now.timestamp()

    healthy = [
        _state(2, updated_at=now),
        _state(6, updated_at=now),
    ]

    assert failsafe._peer_states_ready(
        "kernel_vxlan",
        {2, 6},
        healthy,
        now_epoch=epoch,
    )

    assert not failsafe._peer_states_ready(
        "kernel_vxlan",
        {2, 6},
        healthy[:1],
        now_epoch=epoch,
    )

    wrong_transport = [
        _state(2, updated_at=now),
        _state(6, transport="tp27_fast", updated_at=now),
    ]
    assert not failsafe._peer_states_ready(
        "kernel_vxlan",
        {2, 6},
        wrong_transport,
        now_epoch=epoch,
    )

    one_way = [
        _state(2, updated_at=now),
        _state(6, tunnel=False, updated_at=now),
    ]
    assert not failsafe._peer_states_ready(
        "kernel_vxlan",
        {2, 6},
        one_way,
        now_epoch=epoch,
    )

    stale = [
        _state(2, updated_at=now),
        _state(
            6,
            updated_at=now - timedelta(
                seconds=failsafe.PEER_FRESHNESS_SECONDS + 10,
            ),
        ),
    ]
    assert not failsafe._peer_states_ready(
        "kernel_vxlan",
        {2, 6},
        stale,
        now_epoch=epoch,
    )


def test_modern_delivery_falls_back_to_direct_exit() -> None:
    original_endpoint = failsafe._ORIGINAL_MODERN_TUNNEL_ENDPOINT
    original_gate = failsafe._selected_delivery_tunnel_ready

    exit_node = SimpleNamespace(id=6)

    try:
        failsafe._ORIGINAL_MODERN_TUNNEL_ENDPOINT = (
            lambda db, node, protocol, subscription_id: (
                "193.39.9.222",
                28006,
            )
        )

        failsafe._selected_delivery_tunnel_ready = (
            lambda db, node: False
        )

        # None means V251's live-delivery wrapper keeps the historical direct
        # Exit item unchanged instead of rewriting it to Iran ingress.
        assert failsafe._modern_tunnel_endpoint_v255(
            object(),
            exit_node,
            "hysteria2",
            17,
        ) is None

        failsafe._selected_delivery_tunnel_ready = (
            lambda db, node: True
        )

        assert failsafe._modern_tunnel_endpoint_v255(
            object(),
            exit_node,
            "hysteria2",
            17,
        ) == ("193.39.9.222", 28006)

    finally:
        failsafe._ORIGINAL_MODERN_TUNNEL_ENDPOINT = original_endpoint
        failsafe._selected_delivery_tunnel_ready = original_gate


def test_scope_and_apply_order() -> None:
    assert set(binding.MODERN_TUNNEL_PROTOCOLS) == MODERN
    assert set(protocol_v87._PROTOCOL_ENABLE_ATTR) == LEGACY

    source = inspect.getsource(
        protocol_v87.apply_protocol_dataplane_desired_state_v87
    )

    v251 = source.index("apply_modern_protocol_tunnel_binding_v251()")
    v255 = source.index(
        "apply_modern_protocol_tunnel_delivery_failsafe_v255()"
    )

    assert v251 < v255
    assert "modern_delivery_failsafe=v255" in source


def main() -> None:
    test_two_peer_gate_is_fail_closed()
    test_modern_delivery_falls_back_to_direct_exit()
    test_scope_and_apply_order()

    print(
        "TWINPANEL_MODERN_PROTOCOL_TUNNEL_DELIVERY_FAILSAFE_V255_SMOKE_OK "
        "modern=10 fallback=direct-exit gate=two-peer-fresh-active-transport "
        "legacy_five=unchanged"
    )


if __name__ == "__main__":
    main()
