from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FAST = ROOT / "backend/app/routers/public_connection_payload_fast_v1.py"
LIVE = ROOT / "backend/app/routers/public_connection_hub_live_v5.py"
LEGACY = ROOT / "backend/app/routers/account_delivery.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    fast = FAST.read_text(encoding="utf-8")
    live = LIVE.read_text(encoding="utf-8")
    legacy = LEGACY.read_text(encoding="utf-8")

    require("TWINPANEL_PUBLIC_CONNECT_PAYLOAD_FAST_V1" in fast, "fast payload marker missing")
    require("_stored_info(db, sub)" in fast, "fast payload must reuse stored credentials")
    require("!= \"wireguard\"" in fast, "fast payload must scope eager QR to WireGuard only")
    require("item[\"qr\"] = _qr_data_uri(item[\"config\"])" in fast,
            "WireGuard QR compatibility missing")
    require("_qr_data_uri(item[\"uri\"])" not in fast,
            "fast payload must not eagerly generate V2Ray/Xray QR")

    require("public_connection_payload_fast_v1" in live, "live hub does not import fast payload")
    require("_public_connection_hub_v5_module._public_payload = public_connection_payload_fast_v1" in live,
            "Hub V5 payload hook missing")

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
