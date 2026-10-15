from __future__ import annotations

import json

from . import transport_policy_v20 as v20
from .models import TunnelTransport


# ============================================================
# TWINPANEL AUTO ELIGIBILITY V24
#
# Health and reachability are necessary but they are not throughput metrics.
# A transport may be perfectly healthy at L3 while a provider/path has a hard
# directional bandwidth cap. V24 therefore adds an explicit per-member Auto
# eligibility gate stored inside TunnelTransport.config_text.
#
#   {"auto_eligible": false}
#
# means:
#   * keep the transport installed and health-checkable
#   * keep it selectable in Manual mode
#   * exclude it only from Auto ranking/promotion
#
# Absence of the flag preserves historical behaviour. Malformed config also
# fails open so an unrelated legacy config cannot silently remove a transport
# from Auto. Only an explicit false value blocks Auto.
# ============================================================


_BASE_ENABLED_ROWS = None


def _explicit_false(value: object) -> bool:
    if value is False:
        return True

    if isinstance(value, (int, float)):
        return value == 0

    if isinstance(value, str):
        return value.strip().lower() in {
            "0",
            "false",
            "no",
            "off",
            "disabled",
        }

    return False


def auto_eligible(row: TunnelTransport) -> bool:
    raw = getattr(row, "config_text", None)

    if not raw:
        return True

    try:
        data = json.loads(str(raw))
    except Exception:
        return True

    if not isinstance(data, dict):
        return True

    if "auto_eligible" not in data:
        return True

    return not _explicit_false(
        data.get("auto_eligible")
    )


def enabled_rows_v24(
    rows: list[TunnelTransport],
) -> list[TunnelTransport]:
    base = _BASE_ENABLED_ROWS

    if base is None:
        base = v20._enabled_rows

    return [
        row
        for row in base(rows)
        if auto_eligible(row)
    ]


def install_auto_eligibility_v24() -> None:
    global _BASE_ENABLED_ROWS

    if _BASE_ENABLED_ROWS is None:
        _BASE_ENABLED_ROWS = v20._enabled_rows

    v20._enabled_rows = enabled_rows_v24

    print(
        "TWINPANEL_AUTO_ELIGIBILITY_V24_ACTIVE "
        "manual_unchanged=1 explicit_auto_eligible_false=excluded",
        flush=True,
    )
