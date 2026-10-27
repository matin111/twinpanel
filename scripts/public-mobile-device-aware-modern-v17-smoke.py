from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V11_PATH = ROOT / "backend/app/routers/public_connection_device_actions_v11.py"
V17_PATH = ROOT / "backend/app/routers/public_connection_mobile_protocols_v17.py"
V24_PATH = ROOT / "backend/app/routers/public_connection_canonical_presentation_v24.py"


MODERN = {
    "hysteria2", "tuic", "anytls", "naive", "shadowtls",
    "snell", "mieru", "trusttunnel", "amneziawg", "sudoku",
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
    v24_source = V24_PATH.read_text(encoding="utf-8")
    v17 = load_v17()

    # Legacy V17 remains valid for rollback/history.
    sample = "<!doctype html><html><head><style></style></head><body></body></html>"
    direct = v17.refine_public_connection_mobile_protocols_v17(sample)
    require("TWINPANEL_PUBLIC_CONNECT_MOBILE_PROTOCOLS_V17" in direct, "V17 marker missing")
    require("v17-mobile-stack" in direct, "legacy V17 mobile stack missing")
    require("max-width:720px" in direct, "V17 must remain mobile-only")
    require(v17.refine_public_connection_mobile_protocols_v17(direct) == direct, "V17 is not idempotent")

    # Device detection remains in V11; V24 is the sole active presentation adapter.
    require("navigator.userAgentData" in v11_source, "Client Hints/User-Agent detection regressed")
    require("maxTouchPoints" in v11_source, "iPadOS detection regressed")
    require("body.dataset.tpPlatform=platform" in v11_source, "device platform authority missing")
    require("public_connection_canonical_presentation_v24" in v11_source, "V24 import missing")
    require("refine_public_connection_canonical_presentation_v24(source)" in v11_source, "V24 chain missing")
    require("public_connection_mobile_protocols_v17" not in v11_source, "retired V17 re-entered active V11 chain")
    require("refine_public_connection_mobile_protocols_v17" not in v11_source, "retired V17 is still executed")

    script = v17._MOBILE_PROTOCOLS_V17_SCRIPT.lower()
    for protocol in sorted(MODERN):
        require(protocol in script, f"legacy V17 protocol coverage missing: {protocol}")

    # New authority reuses canonical server DOM and never creates a mobile data model.
    require(".protocol-panel" in v24_source, "V24 canonical protocol panel authority missing")
    require(".server-view" in v24_source, "V24 canonical server view authority missing")
    require("fetch(" not in v24_source, "V24 must not fetch a mobile-only dataset")
    require("json.parse" not in v24_source.lower(), "V24 must not parse/rebuild configs")

    print("PUBLIC_MOBILE_DEVICE_AWARE_MODERN_V17_LEGACY=PASS")
    print("PUBLIC_CANONICAL_PRESENTATION_V24_AUTHORITY=PASS")


if __name__ == "__main__":
    main()
