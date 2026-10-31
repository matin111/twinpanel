from __future__ import annotations

from pathlib import Path


def test_v48_is_installed_before_runtime_composition() -> None:
    package_init = Path("app/__init__.py").read_text(encoding="utf-8")
    assert "_install_xray_grpc_target_isolation_v48()" in package_init


def test_domainless_xray_targets_stay_outside_shared_modern_range() -> None:
    # Importing app executes the production startup compatibility installers,
    # including V48. Do not invoke the full V47 runtime here: that composition
    # rewires many unrelated production hooks and is not needed to verify the
    # target-port authority that caused fresh credential provisioning to fail.
    from app import xray_modern_runtime
    from app.xray_adaptive_three_profiles_v47 import TCP_REALITY_TARGET_OFFSET
    from app.xray_grpc_target_isolation_v48 import GRPC_TARGET_OFFSET_V48
    from app.xray_customer_xhttp_v46 import XHTTP_TARGET_OFFSET_V46

    base_port = 8443
    modern_reserved = set(range(8444, 8453))

    xhttp_port = base_port + int(XHTTP_TARGET_OFFSET_V46)
    tcp_reality_port = base_port + int(TCP_REALITY_TARGET_OFFSET)
    grpc_offset = int(
        xray_modern_runtime.PROFILE_META[
            xray_modern_runtime.PROFILE_GRPC
        ]["offset"]
    )
    grpc_port = base_port + grpc_offset

    assert int(XHTTP_TARGET_OFFSET_V46) == 1004
    assert int(TCP_REALITY_TARGET_OFFSET) == 1005
    assert int(GRPC_TARGET_OFFSET_V48) == 1006
    assert grpc_offset == GRPC_TARGET_OFFSET_V48
    assert (xhttp_port, tcp_reality_port, grpc_port) == (9447, 9448, 9449)
    assert {xhttp_port, tcp_reality_port, grpc_port}.isdisjoint(modern_reserved)
    assert len({xhttp_port, tcp_reality_port, grpc_port}) == 3


def test_v47_domainless_contract_still_requires_grpc() -> None:
    source = Path("app/xray_adaptive_three_profiles_v47.py").read_text(
        encoding="utf-8"
    )
    assert "xray_modern_runtime.PROFILE_GRPC" in source
    assert 'TCP_REALITY_TARGET_OFFSET = 1005' in source
