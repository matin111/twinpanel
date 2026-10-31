from __future__ import annotations

import re
from pathlib import Path


def _int_constant(path: str, name: str) -> int:
    source = Path(path).read_text(encoding="utf-8")
    match = re.search(
        rf"^{re.escape(name)}\s*=\s*(\d+)\s*$",
        source,
        flags=re.MULTILINE,
    )
    if not match:
        raise AssertionError(f"missing integer constant {name} in {path}")
    return int(match.group(1))


package_init = Path("app/__init__.py").read_text(encoding="utf-8")
v48_source = Path("app/xray_grpc_target_isolation_v48.py").read_text(
    encoding="utf-8"
)
v47_source = Path("app/xray_adaptive_three_profiles_v47.py").read_text(
    encoding="utf-8"
)

assert "from .xray_grpc_target_isolation_v48 import" in package_init
assert "_install_xray_grpc_target_isolation_v48()" in package_init
assert 'meta["offset"] = int(GRPC_TARGET_OFFSET_V48)' in v48_source
assert "xray_modern_runtime.PROFILE_GRPC" in v48_source

xhttp_offset = _int_constant(
    "app/xray_customer_xhttp_v46.py",
    "XHTTP_TARGET_OFFSET_V46",
)
tcp_reality_offset = _int_constant(
    "app/xray_adaptive_three_profiles_v47.py",
    "TCP_REALITY_TARGET_OFFSET",
)
grpc_offset = _int_constant(
    "app/xray_grpc_target_isolation_v48.py",
    "GRPC_TARGET_OFFSET_V48",
)

base_port = 8443
modern_reserved = set(range(8444, 8453))
target_ports = (
    base_port + xhttp_offset,
    base_port + tcp_reality_offset,
    base_port + grpc_offset,
)

assert (xhttp_offset, tcp_reality_offset, grpc_offset) == (1004, 1005, 1006)
assert target_ports == (9447, 9448, 9449)
assert set(target_ports).isdisjoint(modern_reserved)
assert len(set(target_ports)) == 3

required_start = v47_source.index("def _required_profiles_v47")
required_end = v47_source.index("def _customer_order_for_item", required_start)
required_source = v47_source[required_start:required_end]
assert "xray_modern_runtime.PROFILE_XHTTP" in required_source
assert "xray_modern_runtime.PROFILE_GRPC" in required_source
assert "PROFILE_TCP_REALITY" in required_source

print(
    "XRAY_GRPC_TARGET_ISOLATION_V48_OK "
    "targets=9447,9448,9449 modern_reserved=8444-8452"
)
