from __future__ import annotations

from fastapi import HTTPException

from app.manual_transport_api_v23 import (
    apply_manual_transport_api_v23,
    set_tunnel_transport_mode_v23,
)
from app.models import Tunnel, TunnelTransport
from app.routers import tunnels


class FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.rows)


class FakeDB:
    def __init__(self, tunnel, rows):
        self.tunnel = tunnel
        self.rows = list(rows)
        self.commits = 0

    def get(self, model, key):
        if model is Tunnel and int(key) == int(self.tunnel.id):
            return self.tunnel
        return None

    def query(self, model):
        if model is TunnelTransport:
            return FakeQuery(self.rows)
        return FakeQuery([])

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        return None


def make_tunnel() -> Tunnel:
    row = Tunnel()
    row.id = 5
    row.mode = "auto"
    row.active_transport = "quic_2027"
    row.preferred_transport = "arq_2027"
    row.latency_ms = 90
    return row


def transport(name: str, *, enabled=True, status="online", latency=82):
    row = TunnelTransport()
    row.tunnel_id = 5
    row.transport = name
    row.enabled = enabled
    row.status = status
    row.priority = 50
    row.latency_ms = latency
    return row


def select(name: str, rows):
    row = make_tunnel()
    db = FakeDB(row, rows)

    result = set_tunnel_transport_mode_v23(
        5,
        tunnels.TunnelTransportModeIn(
            mode="manual",
            transport=name,
        ),
        db,
    )

    return row, db, result


def main() -> None:
    kernel = transport("kernel_gre", latency=82)
    quic = transport("quic_2027", latency=91)

    row, db, result = select(
        "kernel_gre",
        [quic, kernel],
    )

    assert db.commits == 1
    assert row.mode == "manual"
    assert row.active_transport == "kernel_gre"
    assert row.preferred_transport == "kernel_gre"
    assert result["active_transport"] == "kernel_gre"
    assert result["transport_status"] == "online"

    # The rule is registry-driven, not kernel-specific.
    row2, _, result2 = select(
        "quic_2027",
        [quic, kernel],
    )
    assert row2.active_transport == "quic_2027"
    assert result2["active_transport"] == "quic_2027"

    disabled = transport(
        "future_transport",
        enabled=False,
    )
    try:
        select(
            "future_transport",
            [disabled],
        )
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("disabled transport must be rejected")

    offline = transport(
        "future_transport",
        status="offline",
    )
    try:
        select(
            "future_transport",
            [offline],
        )
    except HTTPException as exc:
        assert exc.status_code == 409
    else:
        raise AssertionError("offline transport must be rejected")

    patched = apply_manual_transport_api_v23()
    assert patched == 1
    assert apply_manual_transport_api_v23() == 0

    matches = [
        route
        for route in tunnels.router.routes
        if getattr(route, "path", "")
        == "/v1/tunnels/{tunnel_id}/transport-mode"
        and "POST" in set(getattr(route, "methods", ()) or ())
    ]

    assert len(matches) == 1
    assert matches[0].endpoint is set_tunnel_transport_mode_v23
    assert matches[0].dependant.call is set_tunnel_transport_mode_v23

    print(
        "MANUAL_TRANSPORT_API_V23_SMOKE_OK "
        "selection=registry-driven kernel_gre=selectable future=compatible"
    )


if __name__ == "__main__":
    main()
