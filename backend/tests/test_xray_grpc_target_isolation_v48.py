from __future__ import annotations

from pathlib import Path


def test_v48_is_installed_before_runtime_composition() -> None:
    package_init = Path("app/__init__.py").read_text(encoding="utf-8")
    assert "_install_xray_grpc_target_isolation_v48()" in package_init


def test_domainless_xray_targets_stay_outside_shared_modern_range() -> None:
    from app import xray_modern_runtime
    from app.xray_adaptive_three_profiles_v47 import (
        TCP_REALITY_TARGET_OFFSET,
        apply_xray_adaptive_three_profiles_v47,
    )
    from app.xray_grpc_target_isolation_v48 import GRPC_TARGET_OFFSET_V48
    from app.xray_customer_xhttp_v46 import XHTTP_TARGET_OFFSET_V46

    apply_xray_adaptive_three_profiles_v47()

    base_port = 8443
    modern_reserved = set(range(8444, 8453))

    xhttp_port = base_port + int(XHTTP_TARGET_OFFSET_V46)
    tcp_reality_port = base_port + int(TCP_REALITY_TARGET_OFFSET)
    grpc_port = base_port + int(
        xray_modern_runtime.PROFILE_META[xray_modern_runtime.PROFILE_GRPC]["offset"]
    )

    assert int(XHTTP_TARGET_OFFSET_V46) == 1004
    assert int(TCP_REALITY_TARGET_OFFSET) == 1005
    assert int(GRPC_TARGET_OFFSET_V48) == 1006
    assert (xhttp_port, tcp_reality_port, grpc_port) == (9447, 9448, 9449)
    assert {xhttp_port, tcp_reality_port, grpc_port}.isdisjoint(modern_reserved)
    assert len({xhttp_port, tcp_reality_port, grpc_port}) == 3
