from __future__ import annotations

from app.manual_transport_report_guard_v22 import (
    apply_manual_transport_report_guard_v22,
    enforce_manual_report_authority,
)
from app.models import Tunnel, TunnelPeerState


class FakeSession:
    def __init__(self, *, new=(), dirty=()):
        self.new = list(new)
        self.dirty = list(dirty)


def tunnel(*, mode: str, active: str, preferred: str) -> Tunnel:
    row = Tunnel()
    row.id = 5
    row.mode = mode
    row.active_transport = active
    row.preferred_transport = preferred
    return row


def peer() -> TunnelPeerState:
    row = TunnelPeerState()
    row.tunnel_id = 5
    row.node_id = 3
    return row


def main() -> None:
    # Stale Agent report must not undo a newly selected Manual transport.
    manual = tunnel(
        mode="manual",
        active="quic_2027",
        preferred="kernel_gre",
    )
    changed = enforce_manual_report_authority(
        FakeSession(
            dirty=(manual, peer()),
        )
    )
    assert changed == 1
    assert manual.active_transport == "kernel_gre"

    # Auto remains manager-owned and untouched by this guard.
    auto = tunnel(
        mode="auto",
        active="quic_2027",
        preferred="kernel_gre",
    )
    changed = enforce_manual_report_authority(
        FakeSession(
            dirty=(auto, peer()),
        )
    )
    assert changed == 0
    assert auto.active_transport == "quic_2027"

    # Manual state which already matches its requested transport is unchanged.
    stable = tunnel(
        mode="manual",
        active="kernel_gre",
        preferred="kernel_gre",
    )
    changed = enforce_manual_report_authority(
        FakeSession(
            dirty=(stable, peer()),
        )
    )
    assert changed == 0
    assert stable.active_transport == "kernel_gre"

    # Non-report transactions are outside this compatibility guard.
    non_report = tunnel(
        mode="manual",
        active="quic_2027",
        preferred="kernel_gre",
    )
    changed = enforce_manual_report_authority(
        FakeSession(
            dirty=(non_report,),
        )
    )
    assert changed == 0
    assert non_report.active_transport == "quic_2027"

    # Registration must be idempotent.
    apply_manual_transport_report_guard_v22()
    apply_manual_transport_report_guard_v22()

    print(
        "MANUAL_TRANSPORT_REPORT_GUARD_V22_SMOKE_OK "
        "manual=authoritative auto=manager-owned report=telemetry"
    )


if __name__ == "__main__":
    main()
