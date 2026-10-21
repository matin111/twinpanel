from __future__ import annotations

from pathlib import Path

from app.modern_protocol_dispatch import SINGBOX_PROTOCOLS, redacted_preview
from app.protocol_catalog import PROTOCOL_CATALOG, catalog_payload, resolve_settings


STANDALONE = {"mieru", "trusttunnel", "amneziawg", "sudoku"}
EXPECTED_READY = {
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
    *STANDALONE,
}


def main() -> None:
    assert STANDALONE <= SINGBOX_PROTOCOLS
    assert EXPECTED_READY <= SINGBOX_PROTOCOLS

    by_key = {item["key"]: item for item in catalog_payload()}
    for key in EXPECTED_READY:
        assert key in by_key, key
        assert by_key[key]["runtime_status"] == "ready", key
        assert by_key[key]["installable"] is True, key

        preset, settings, _warnings = resolve_settings(key, "recommended", {})
        assert preset == "recommended"
        preview = redacted_preview(
            key,
            int(PROTOCOL_CATALOG[key]["default_port"]),
            settings,
        )
        assert preview["listen_port"] == int(PROTOCOL_CATALOG[key]["default_port"])

    assert PROTOCOL_CATALOG["sudoku"]["transport"] == "tcp"
    assert int(PROTOCOL_CATALOG["mieru"]["default_port"]) == 8450
    assert int(PROTOCOL_CATALOG["trusttunnel"]["default_port"]) == 8451
    assert int(PROTOCOL_CATALOG["amneziawg"]["default_port"]) == 8452
    assert int(PROTOCOL_CATALOG["sudoku"]["default_port"]) == 8453

    root = Path(__file__).resolve().parents[2]
    main_py = (root / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    v3 = "app.include_router(modern_protocol_admin_v3_router)"
    legacy = "app.include_router(vpn_settings_router)"
    assert v3 in main_py
    assert legacy in main_py
    assert main_py.index(v3) < main_py.index(legacy)

    runtime_py = (root / "backend" / "app" / "standalone_protocol_runtime.py").read_text(
        encoding="utf-8"
    )
    for version in ("3.38.1", "1.1.0", "0.5.1"):
        assert version in runtime_py
    for digest in (
        "2c7c0be33d34cf126187d97c17484a34b5c62b764c96b0a88ec4cbc7660d72c9",
        "91c2ea3db7416a01b5258a4c047ec22890490bc55e1b194206031aa75144f0e7",
        "a9ebfb7e359d7f667062400a098e117e4e2bed55c65aea099e949129953028d0",
    ):
        assert digest in runtime_py

    print("MODERN_PROTOCOL_RUNTIME_V3_SMOKE_OK")


if __name__ == "__main__":
    main()
