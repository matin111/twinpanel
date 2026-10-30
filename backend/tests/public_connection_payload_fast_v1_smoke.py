from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAST = ROOT / "backend/app/routers/public_connection_payload_fast_v1.py"
LIVE = ROOT / "backend/app/routers/public_connection_hub_live_v5.py"
LEGACY = ROOT / "backend/app/routers/account_delivery.py"
V13 = ROOT / "backend/app/routers/public_connection_modern_delivery_v13.py"
V14 = ROOT / "backend/app/routers/public_connection_modern_names_v14.py"
V15 = ROOT / "backend/app/routers/public_connection_modern_import_v15.py"
V16 = ROOT / "backend/app/routers/public_connection_modern_delivery_v16.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    fast = FAST.read_text(encoding="utf-8")
    live = LIVE.read_text(encoding="utf-8")
    legacy = LEGACY.read_text(encoding="utf-8")
    refiners = {
        "v13": V13.read_text(encoding="utf-8"),
        "v14": V14.read_text(encoding="utf-8"),
        "v15": V15.read_text(encoding="utf-8"),
        "v16": V16.read_text(encoding="utf-8"),
    }

    require("TWINPANEL_PUBLIC_CONNECT_PAYLOAD_FAST_V1" in fast, "fast payload marker missing")
    require("_stored_info(db, sub)" in fast, "fast payload must reuse stored credentials")
    require("!= \"wireguard\"" in fast, "fast payload must scope eager QR to WireGuard only")
    require("item[\"qr\"] = _qr_data_uri(item[\"config\"])" in fast,
            "WireGuard QR compatibility missing")
    require("_qr_data_uri(item[\"uri\"])" not in fast,
            "fast payload must not eagerly generate V2Ray/Xray QR")

    require("TWINPANEL_PUBLIC_CONNECT_REQUEST_PAYLOAD_CACHE_V2" in fast,
            "request-local payload cache marker missing")
    require("cache_key = (_CACHE_PREFIX, int(sub.id))" in fast,
            "payload cache must be subscription-scoped")
    require("cached = db.info.get(cache_key)" in fast,
            "payload cache must use the request Session.info boundary")
    require("return deepcopy(cached)" in fast,
            "cache hits must be isolated from presentation mutations")
    require("db.info[cache_key] = deepcopy(info)" in fast,
            "canonical cached payload must be isolated from the first caller")

    require("public_connection_payload_fast_v1" in live, "live hub does not import fast payload")
    require("_public_connection_hub_v5_module._public_payload = public_connection_payload_fast_v1" in live,
            "Hub V5 payload hook missing")

    require("install_public_connection_fast_payload_refiners_v1" in fast,
            "presentation refiner fast-payload installer missing")
    for module_name in (
        "public_connection_modern_delivery_v13",
        "public_connection_modern_names_v14",
        "public_connection_modern_import_v15",
        "public_connection_modern_delivery_v16",
    ):
        require(module_name in fast, f"fast payload installer missing {module_name}")

    # These refiners still contain their historical symbol references, but the
    # active Hub import must rebind them before rendering. This prevents future
    # cleanup from silently dropping one of the presentation stages.
    for name, source in refiners.items():
        require("_public_payload(db, sub)" in source,
                f"{name} no longer matches the expected presentation payload call")

    # Legacy behavior stays available to unrelated account-delivery endpoints.
    require("elif cred[\"protocol\"] == \"v2ray\"" in legacy,
            "legacy V2Ray QR behavior was unexpectedly removed globally")
    require("item[\"qr\"] = _qr_data_uri(item[\"uri\"])" in legacy,
            "legacy V2Ray QR generator drifted")

    for forbidden in (
        "db.add(", "db.commit(", "ProtocolCredential(", "subprocess", "iptables", "nft ",
    ):
        require(forbidden not in fast, f"fast payload escaped read-only scope: {forbidden}")

    print("PUBLIC_CONNECTION_PAYLOAD_FAST_V1_SMOKE=PASS")


if __name__ == "__main__":
    main()
