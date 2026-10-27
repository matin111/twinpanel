from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.routers.public_connection_device_actions_v11 import (  # noqa: E402
    refine_public_connection_device_actions_v11,
)
from app.routers.public_connection_mobile_protocols_v17 import (  # noqa: E402
    _MOBILE_PROTOCOLS_V17_SCRIPT,
    refine_public_connection_mobile_protocols_v17,
)


MODERN = {
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
    "mieru",
    "trusttunnel",
    "amneziawg",
    "sudoku",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    sample = "<!doctype html><html><head><style></style></head><body></body></html>"

    direct = refine_public_connection_mobile_protocols_v17(sample)
    require("TWINPANEL_PUBLIC_CONNECT_MOBILE_PROTOCOLS_V17" in direct, "V17 marker missing")
    require("v17-mobile-stack" in direct, "unified mobile stack missing")
    require("max-width:720px" in direct, "V17 must remain mobile-only")

    chained = refine_public_connection_device_actions_v11(sample)
    require("TWINPANEL_PUBLIC_CONNECT_DEVICE_ACTIONS_V11" in chained, "V11 device detector missing")
    require("TWINPANEL_PUBLIC_CONNECT_MOBILE_PROTOCOLS_V17" in chained, "V11 must chain V17")
    require("body.dataset.tpPlatform=platform" in chained, "device platform authority missing")
    require("navigator.userAgentData" in chained, "Client Hints/User-Agent detection regressed")
    require("maxTouchPoints" in chained, "iPadOS detection regressed")

    script = _MOBILE_PROTOCOLS_V17_SCRIPT.lower()
    for protocol in sorted(MODERN):
        require(protocol in script, f"Modern protocol missing from mobile renderer: {protocol}")

    require("body.dataset.tpplatform" in script, "V17 must consume V11 platform authority")
    require(".server-view" in script, "V17 must derive rows from real server views")
    require(".v13-modern-action" in script, "V17 must reuse canonical Modern actions")
    require("data-v13-platform" in script, "V17 must select the app for the detected OS")
    require(".v13-karing-import" in script, "Karing import action must be preserved")
    require("credential" not in script, "technical Credential text must not leak into mobile cards")
    require("runtime" not in script, "technical Runtime text must not leak into mobile cards")

    # Idempotence protects the refinement chain from duplicated scripts/styles.
    repeated = refine_public_connection_device_actions_v11(chained)
    require(repeated == chained, "V11/V17 refinement chain is not idempotent")

    print("PUBLIC_MOBILE_DEVICE_AWARE_MODERN_V17=PASS")


if __name__ == "__main__":
    main()
