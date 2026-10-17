from __future__ import annotations

import json

from . import tp2027_multi_exit_v18 as v18


# ============================================================
# TWINPANEL PUBLIC-DIRECT TUNING V19
#
# Production traces on the Iran -> USA public-direct path showed that the
# 8-lane TCP/QUIC processes establish successfully, but an idle/degraded lane
# can terminate the whole process. TCP carried valid TUN packets while several
# sibling lanes repeatedly timed out/reset. For the public-direct runtime we
# therefore prefer one stable stream/connection over eight fragile siblings.
#
# KCP and ARQ are intentionally unchanged.
# ============================================================


PUBLIC_DIRECT_LANES = {
    "tcp_2027": 1,
    "quic_2027": 1,
}

_ORIGINAL_PUBLIC_SERVICE_UNIT = v18._public_service_unit
_ORIGINAL_CONFIG_TEXT = v18._config_text_v18


def _public_service_unit_v19(
    transport: str,
    tunnel_id: int,
    *,
    role: str,
    exit_public_ip: str,
) -> str:
    unit = _ORIGINAL_PUBLIC_SERVICE_UNIT(
        transport,
        tunnel_id,
        role=role,
        exit_public_ip=exit_public_ip,
    )

    lanes = PUBLIC_DIRECT_LANES.get(str(transport))
    if lanes is not None:
        unit = unit.replace("--lanes 8", f"--lanes {int(lanes)}")

    return unit


def _config_text_v19(
    transport: str,
    tunnel_id: int,
    exit_public_ip: str,
) -> str:
    payload = json.loads(
        _ORIGINAL_CONFIG_TEXT(
            transport,
            tunnel_id,
            exit_public_ip,
        )
    )

    lanes = PUBLIC_DIRECT_LANES.get(str(transport))
    if lanes is not None:
        payload["lanes"] = int(lanes)
        payload["stability_profile"] = "single_lane_v19"

    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def apply_public_direct_tuning_v19() -> None:
    v18._public_service_unit = _public_service_unit_v19
    v18._config_text_v18 = _config_text_v19

    print(
        "TWINPANEL_PUBLIC_DIRECT_TUNING_V19_ACTIVE "
        "tcp_lanes=1 quic_lanes=1 kcp_unchanged=1 arq_unchanged=1",
        flush=True,
    )
