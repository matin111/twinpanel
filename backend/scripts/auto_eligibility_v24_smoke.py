from __future__ import annotations

from app.auto_eligibility_v24 import (
    auto_eligible,
    enabled_rows_v24,
    install_auto_eligibility_v24,
)
from app.models import TunnelTransport
from app import transport_policy_v20 as v20


def row(
    name: str,
    *,
    enabled: bool = True,
    config_text: str | None = None,
) -> TunnelTransport:
    item = TunnelTransport()
    item.transport = name
    item.enabled = enabled
    item.config_text = config_text
    item.priority = 50
    item.id = 1
    return item


def main() -> None:
    install_auto_eligibility_v24()
    install_auto_eligibility_v24()

    quic = row(
        "quic_2027",
        config_text="{}",
    )

    kernel_blocked = row(
        "kernel_gre",
        config_text='{"auto_eligible": false, "auto_block_reason": "measured_path"}',
    )

    kernel_allowed = row(
        "kernel_gre",
        config_text='{"auto_eligible": true}',
    )

    malformed = row(
        "kernel_gre",
        config_text="{not-json",
    )

    disabled = row(
        "quic_2027",
        enabled=False,
        config_text="{}",
    )

    assert auto_eligible(quic) is True
    assert auto_eligible(kernel_blocked) is False
    assert auto_eligible(kernel_allowed) is True
    assert auto_eligible(malformed) is True

    selected = enabled_rows_v24(
        [
            quic,
            kernel_blocked,
            disabled,
        ]
    )

    assert quic in selected
    assert kernel_blocked not in selected
    assert disabled not in selected

    selected2 = v20._enabled_rows(
        [
            quic,
            kernel_allowed,
        ]
    )

    assert quic in selected2
    assert kernel_allowed in selected2

    print(
        "AUTO_ELIGIBILITY_V24_SMOKE_OK "
        "manual_preserved=1 explicit_false_excluded=1 default_eligible=1"
    )


if __name__ == "__main__":
    main()
