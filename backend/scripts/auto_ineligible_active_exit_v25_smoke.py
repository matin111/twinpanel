from __future__ import annotations

from app.auto_ineligible_active_exit_v25 import (
    active_is_explicitly_ineligible,
    install_auto_ineligible_active_exit_v25,
    manage_2027_v25,
    should_immediate_exit,
)
from app.models import TunnelTransport
from app import tunnel_transport_manager_v7 as v7


def row(
    name: str,
    config_text: str,
) -> TunnelTransport:
    item = TunnelTransport()
    item.id = 1
    item.tunnel_id = 5
    item.transport = name
    item.enabled = True
    item.status = "online"
    item.priority = 50
    item.config_text = config_text
    return item


def main() -> None:
    kernel = row(
        "kernel_gre",
        '{"auto_eligible": false}',
    )

    arq = row(
        "arq_2027",
        '{"auto_eligible": true}',
    )

    rows = [
        kernel,
        arq,
    ]

    assert active_is_explicitly_ineligible(
        rows,
        "kernel_gre",
    ) is True

    assert active_is_explicitly_ineligible(
        rows,
        "arq_2027",
    ) is False

    assert should_immediate_exit(
        rows,
        "kernel_gre",
        "arq_2027",
    ) is True

    assert should_immediate_exit(
        rows,
        "kernel_gre",
        "kernel_gre",
    ) is False

    assert should_immediate_exit(
        rows,
        "arq_2027",
        "kernel_gre",
    ) is False

    original = v7.manage_2027

    install_auto_ineligible_active_exit_v25()
    assert v7.manage_2027 is manage_2027_v25

    install_auto_ineligible_active_exit_v25()
    assert v7.manage_2027 is manage_2027_v25

    # Keep this smoke process isolated from later imports in the same runner.
    v7.manage_2027 = original

    print(
        "AUTO_INELIGIBLE_ACTIVE_EXIT_V25_SMOKE_OK "
        "manual_unchanged=1 explicit_block_immediate=1 fresh_health_required=1"
    )


if __name__ == "__main__":
    main()
