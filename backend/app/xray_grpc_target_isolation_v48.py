from __future__ import annotations

from . import xray_modern_runtime


GRPC_TARGET_OFFSET_V48 = 1006
_runtime_applied = False


def install() -> None:
    global _runtime_applied

    if _runtime_applied:
        return

    meta = xray_modern_runtime.PROFILE_META.get(
        xray_modern_runtime.PROFILE_GRPC
    )
    if not isinstance(meta, dict):
        raise RuntimeError("gRPC Reality profile metadata is missing")

    # The shared Modern protocol runtime owns 8444..8452. V47 already isolates
    # XHTTP at base+1004 and TCP Reality at base+1005, but gRPC Reality still
    # inherits the historical base+2 target (8445 for default base 8443).
    # Domainless Xray provisioning requires all three profiles, so that collision
    # makes _ensure_modern_xray fail before ProtocolCredential persistence.
    meta["offset"] = int(GRPC_TARGET_OFFSET_V48)

    _runtime_applied = True
    print(
        "TWINPANEL_XRAY_GRPC_TARGET_ISOLATION_V48_ACTIVE "
        "grpc_target_offset=1006 modern_reserved=8444-8452",
        flush=True,
    )
