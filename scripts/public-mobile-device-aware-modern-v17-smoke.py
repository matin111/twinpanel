from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V11_PATH = ROOT / "backend/app/routers/public_connection_device_actions_v11.py"
V17_PATH = ROOT / "backend/app/routers/public_connection_mobile_protocols_v17.py"


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


def load_v17():
    spec = spec_from_file_location("twinpanel_mobile_protocols_v17", V17_PATH)
    require(spec is not None and spec.loader is not None, "could not load V17 module spec")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    v11_source = V11_PATH.read_text(encoding="utf-8")
    v17_source = V17_PATH.read_text(encoding="utf-8")
    v17 = load_v17()

    sample = "<!doctype html><html><head><style></style></head><body></body></html>"
    direct = v17.refine_public_connection_mobile_protocols_v17(sample)
    require("TWINPANEL_PUBLIC_CONNECT_MOBILE_PROTOCOLS_V17" in direct, "V17 marker missing")
    require("v17-mobile-stack" in direct, "unified mobile stack missing")
    require("max-width:720px" in direct, "V17 must remain mobile-only")
    require(v17.refine_public_connection_mobile_protocols_v17(direct) == direct, "V17 is not idempotent")

    # V11 remains the single device detector and chains the additive V17 renderer.
    require("navigator.userAgentData" in v11_source, "Client Hints/User-Agent detection regressed")
    require("maxTouchPoints" in v11_source, "iPadOS detection regressed")
    require("body.dataset.tpPlatform=platform" in v11_source, "device platform authority missing")
    require("from .public_connection_mobile_protocols_v17 import" in v11_source, "V11 does not import V17")
    require("return refine_public_connection_mobile_protocols_v17(source)" in v11_source, "V11 does not chain V17")

    script = v17._MOBILE_PROTOCOLS_V17_SCRIPT.lower()
    for protocol in sorted(MODERN):
        require(protocol in script, f"Modern protocol missing from mobile renderer: {protocol}")

    require("body.dataset.tpplatform" in script, "V17 must consume V11 platform authority")
    require(".server-view" in script, "V17 must derive rows from real server views")
    require(".v13-modern-action" in script, "V17 must reuse canonical Modern actions")
    require("data-v13-platform" in script, "V17 must select the app for the detected OS")
    require("v13-karing-import" in script, "Karing import action must be preserved")
    require("credential" not in script, "technical Credential text must not leak into mobile cards")
    require("runtime" not in script, "technical Runtime text must not leak into mobile cards")

    # Guard desktop and source scope as well as the generated HTML scope.
    require("@media(max-width:720px)" in v17_source, "mobile CSS scope missing")
    require("body.v17-ready .protocol-panel" in v17_source, "legacy phone panels are not hidden after V17 activation")

    print("PUBLIC_MOBILE_DEVICE_AWARE_MODERN_V17=PASS")


if __name__ == "__main__":
    main()
