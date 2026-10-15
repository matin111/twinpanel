from __future__ import annotations

import math

from app import kernel_gre_auto_v21 as v21
from app.kernel_gre_health_sampling_v26 import (
    KERNEL_GRE_HEALTH_PING_COUNT,
    KERNEL_GRE_HEALTH_PING_INTERVAL,
    install_kernel_gre_health_sampling_v26,
    peer_snapshot_v26,
)


def main() -> None:
    minimum = math.ceil(
        100.0 / float(v21.MAX_AUTO_PACKET_LOSS_PCT)
    )

    assert KERNEL_GRE_HEALTH_PING_COUNT >= minimum
    assert KERNEL_GRE_HEALTH_PING_COUNT == 20
    assert KERNEL_GRE_HEALTH_PING_INTERVAL == 0.1

    one_loss_pct = (
        100.0
        / float(KERNEL_GRE_HEALTH_PING_COUNT)
    )

    two_loss_pct = (
        200.0
        / float(KERNEL_GRE_HEALTH_PING_COUNT)
    )

    assert one_loss_pct <= v21.MAX_AUTO_PACKET_LOSS_PCT
    assert two_loss_pct > v21.MAX_AUTO_PACKET_LOSS_PCT

    original = v21._peer_snapshot

    install_kernel_gre_health_sampling_v26()
    install_kernel_gre_health_sampling_v26()

    assert v21._peer_snapshot is peer_snapshot_v26
    assert v21._peer_snapshot is not original

    print(
        "KERNEL_GRE_HEALTH_SAMPLING_V26_SMOKE_OK "
        f"samples={KERNEL_GRE_HEALTH_PING_COUNT} "
        f"one_loss_pct={one_loss_pct:.1f} "
        f"two_loss_pct={two_loss_pct:.1f} "
        f"limit={v21.MAX_AUTO_PACKET_LOSS_PCT:.1f}"
    )


if __name__ == "__main__":
    main()
