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


def test_v210_underlay_preflight_combines_prerequisites_and_persisted_evidence():
    api = read("lib/modern-transport-api.ts")

    assert 'SPOOF_UNDERLAY_REASON_V210="underlay_incompatible:reverse_carrier_not_reaching_iran"' in api
    assert "async function checkSpoofCompatibilityV210" in api
    assert "Promise.all([" in api
    assert "/modern-transports/spoof_wg/compatibility-check" in api
    assert "/modern-transports`)" in api

    for token in (
        "row?.last_error",
        "row?.auto_block_reason",
        "row?.quarantine_until_epoch",
        'verdict="known_incompatible_active"',
        'verdict="known_incompatible_observed"',
        'verdict="qualified_online"',
        'verdict="eligible_unproven"',
        'verdict="configuration_required"',
        'verdict="prerequisite_blocked"',
        "compatible:Boolean(prerequisite.compatible)&&!knownIncompatible",
        "ready_for_install:Boolean(prerequisite.ready_for_install)&&!knownIncompatible",
        "retry_blocked:Boolean(knownIncompatible&&quarantineActive)",
        "preflight_version:210",
        "checkSpoofCompatibility:checkSpoofCompatibilityV210",
    ):
        assert token in api, token


def test_v210_known_underlay_failure_cannot_be_labeled_ready_by_host_prerequisites():
    api = read("lib/modern-transport-api.ts")

    start = api.index("async function checkSpoofCompatibilityV210")
    end = api.index("export const modernTransportApi", start)
    preflight = api[start:end]

    evidence_pos = preflight.index("const evidenceObserved=")
    compatibility_pos = preflight.index(
        "compatible:Boolean(prerequisite.compatible)&&!knownIncompatible"
    )
    ready_pos = preflight.index(
        "ready_for_install:Boolean(prerequisite.ready_for_install)&&!knownIncompatible"
    )

    assert evidence_pos < compatibility_pos < ready_pos
    assert "v206_v208_failure_evidence" in preflight
    assert "underlay_reason:knownIncompatible?SPOOF_UNDERLAY_REASON_V210:null" in preflight
    assert "blockers=Array.from(new Set([" in preflight


def test_v210_preflight_is_read_only_and_does_not_claim_untested_underlay_compatibility():
    api = read("lib/modern-transport-api.ts")

    start = api.index("async function checkSpoofCompatibilityV210")
    end = api.index("export const modernTransportApi", start)
    preflight = api[start:end]

    assert "host-prerequisite" in preflight
    assert "does not generate spoofed traffic" in preflight
    assert "cannot prove an untested provider underlay compatible" in preflight

    for forbidden in (
        "installTransport(",
        "/install",
        "/select-manual",
        "configureSpoof",
        "iptables",
        "nft ",
        "ip route",
        "ip link",
        "systemctl",
        "spoof-port",
        "udp dport",
    ):
        assert forbidden not in preflight, forbidden
