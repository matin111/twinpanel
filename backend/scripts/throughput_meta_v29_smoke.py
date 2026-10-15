from __future__ import annotations

import json
from types import SimpleNamespace

from app import throughput_auto_v27 as v27
from app.throughput_meta_v29 import (
    benchmark_meta_v29,
    install_throughput_meta_v29,
)


def row(name: str, config: dict | None = None):
    return SimpleNamespace(
        transport=name,
        config_text=json.dumps(config or {}),
    )


def main() -> None:
    backhaul5 = benchmark_meta_v29(row("backhaul"), 5)
    assert backhaul5 == {
        "transport": "backhaul",
        "interface": "bh5",
        "iran_ip": "10.253.15.1",
        "exit_ip": "10.253.15.2",
    }, backhaul5

    ssh5 = benchmark_meta_v29(row("ssh_tun"), 5)
    assert ssh5 == {
        "transport": "ssh_tun",
        "interface": "tun5",
        "iran_ip": "10.64.0.21",
        "exit_ip": "10.64.0.22",
    }, ssh5

    # Multi-exit sibling addressing remains deterministic and isolated.
    backhaul9 = benchmark_meta_v29(row("backhaul"), 9)
    assert backhaul9 == {
        "transport": "backhaul",
        "interface": "bh9",
        "iran_ip": "10.253.19.1",
        "exit_ip": "10.253.19.2",
    }, backhaul9

    ssh9 = benchmark_meta_v29(row("ssh_tun"), 9)
    assert ssh9 == {
        "transport": "ssh_tun",
        "interface": "tun9",
        "iran_ip": "10.64.0.37",
        "exit_ip": "10.64.0.38",
    }, ssh9

    # Existing persisted V27 metadata must remain authoritative.
    existing = benchmark_meta_v29(
        row(
            "quic_2027",
            {
                "interface": "tp27q5",
                "iran_ip": "10.252.73.1",
                "exit_ip": "10.252.73.2",
            },
        ),
        5,
    )
    assert existing == {
        "transport": "quic_2027",
        "interface": "tp27q5",
        "iran_ip": "10.252.73.1",
        "exit_ip": "10.252.73.2",
    }, existing

    unknown = benchmark_meta_v29(row("gost_tun"), 5)
    assert unknown is None, unknown

    original = v27._benchmark_meta
    install_throughput_meta_v29()
    assert v27._benchmark_meta is benchmark_meta_v29

    hooked = v27._benchmark_meta(row("backhaul"), 5)
    assert hooked == backhaul5, hooked

    # Restore for smoke isolation.
    v27._benchmark_meta = original

    print(
        "THROUGHPUT_META_V29_SMOKE_OK "
        "backhaul5=bh5/10.253.15.1-10.253.15.2 "
        "ssh5=tun5/10.64.0.21-10.64.0.22 "
        "multi_exit=1 existing_meta_preserved=1 runtime_hook=1"
    )


if __name__ == "__main__":
    main()
