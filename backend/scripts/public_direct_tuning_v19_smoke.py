from __future__ import annotations

import json

from app import tp2027_multi_exit_v18 as v18
from app.public_direct_tuning_v19 import apply_public_direct_tuning_v19


def main() -> None:
    apply_public_direct_tuning_v19()

    tcp = v18._public_service_unit(
        "tcp_2027",
        9,
        role="iran",
        exit_public_ip="64.49.12.176",
    )
    quic = v18._public_service_unit(
        "quic_2027",
        9,
        role="iran",
        exit_public_ip="64.49.12.176",
    )
    kcp = v18._public_service_unit(
        "kcp_2027",
        9,
        role="iran",
        exit_public_ip="64.49.12.176",
    )

    assert "--peer 64.49.12.176:45209" in tcp
    assert "--lanes 1" in tcp
    assert "--lanes 8" not in tcp

    assert "--peer 64.49.12.176:45309" in quic
    assert "--lanes 1" in quic
    assert "--lanes 8" not in quic

    assert "--peer 64.49.12.176:45109" in kcp
    assert "--fec-data 20 --fec-parity 2" in kcp

    tcp_config = json.loads(
        v18._config_text_v18(
            "tcp_2027",
            9,
            "64.49.12.176",
        )
    )
    quic_config = json.loads(
        v18._config_text_v18(
            "quic_2027",
            9,
            "64.49.12.176",
        )
    )
    kcp_config = json.loads(
        v18._config_text_v18(
            "kcp_2027",
            9,
            "64.49.12.176",
        )
    )

    assert tcp_config["carrier"] == "public_direct"
    assert tcp_config["multi_exit_safe"] is True
    assert tcp_config["lanes"] == 1
    assert tcp_config["stability_profile"] == "single_lane_v19"

    assert quic_config["lanes"] == 1
    assert quic_config["stability_profile"] == "single_lane_v19"

    assert "lanes" not in kcp_config
    assert kcp_config["multi_exit_safe"] is True

    print("PUBLIC_DIRECT_TUNING_V19_SMOKE_OK")


if __name__ == "__main__":
    main()
