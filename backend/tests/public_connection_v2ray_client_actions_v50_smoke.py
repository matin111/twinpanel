from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "backend/app/routers/public_connection_v2ray_multilink_action_v44.py"


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")
    required = [
        "v2rayng://install-sub?url=",
        "v2rayng://install-config?url=",
        "v2rayN",
        "v2rayNG",
        "V2Box",
        "کپی لینک برای "+"'+client",
        "ارسال همه به v2rayNG",
        "ارسال به v2rayNG",
        "کپی کانفیگ برای "+"'+client",
        "کپی لینک اشتراک",
    ]
    missing = [value for value in required if value not in source]
    assert not missing, f"missing device-aware V2Ray actions: {missing}"
    assert "ارسال همه به Karing" not in source
    assert "karing://install-config" not in source
    print("public connection V2Ray device-aware client actions smoke: OK")


if __name__ == "__main__":
    main()
