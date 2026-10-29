from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v207_frontend_failed_install_forces_authoritative_refresh():
    api = read("lib/modern-transport-api.ts")
    wrapper = read("components/smart-transports-runtime-v27.tsx")

    event = "twinpanel-modern-transport-authority-refresh-v207"
    assert event in api
    assert "async function installTransport" in api
    assert "notifyAuthorityRefresh();" in api
    assert "install:installTransport" in api

    catch_pos = api.index("}catch(reason){", api.index("async function installTransport"))
    refresh_pos = api.index("notifyAuthorityRefresh();", catch_pos)
    throw_pos = api.index("throw reason;", refresh_pos)
    assert catch_pos < refresh_pos < throw_pos

    assert "MODERN_TRANSPORT_AUTHORITY_REFRESH_EVENT" in wrapper
    assert "window.addEventListener(MODERN_TRANSPORT_AUTHORITY_REFRESH_EVENT,refresh)" in wrapper
    assert "window.removeEventListener(MODERN_TRANSPORT_AUTHORITY_REFRESH_EVENT,refresh)" in wrapper
    assert "setAuthorityEpoch(value=>value+1)" in wrapper
    assert "<SmartTransportsRuntimeV26 key={authorityEpoch}/>" in wrapper


def test_v207_frontend_refresh_is_state_only_not_dataplane():
    api = read("lib/modern-transport-api.ts")
    wrapper = read("components/smart-transports-runtime-v27.tsx")
    joined = api + "\n" + wrapper

    for forbidden in (
        "iptables",
        "nft ",
        "ip route",
        "ip link",
        "systemctl",
        "udp dport",
        "spoof-port",
    ):
        assert forbidden not in joined, forbidden
