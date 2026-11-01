from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_account_provisioning_has_independent_protocol_deadlines() -> None:
    source = (ROOT / "backend/app/routers/modern_account_delivery_v1.py").read_text(
        encoding="utf-8"
    )

    assert "TOTAL_PROVISION_TIMEOUT_SECONDS" not in source
    assert '"v2ray": 30.0' in source
    assert '"openvpn": 60.0' in source
    assert "DEFAULT_PROTOCOL_PROVISION_TIMEOUT_SECONDS = 45.0" in source
    assert "from ..services.hard_async_timeout import await_hard_timeout" in source
    assert source.count("await await_hard_timeout(") >= 2
    assert "timeout_seconds=timeout" in source
    assert "timeout_seconds=QUOTA_SYNC_TIMEOUT_SECONDS" in source
    assert "Provisioning timeout after" in source
    assert "Quota sync timeout after" in source
    assert "Provisioning total deadline exceeded before this protocol" not in source
