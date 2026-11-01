from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_account_provisioning_has_protocol_and_total_deadlines() -> None:
    source = (ROOT / "backend/app/routers/modern_account_delivery_v1.py").read_text(
        encoding="utf-8"
    )

    assert "TOTAL_PROVISION_TIMEOUT_SECONDS = 120.0" in source
    assert '"v2ray": 30.0' in source
    assert '"openvpn": 60.0' in source
    assert "await asyncio.wait_for(" in source
    assert "Provisioning timeout after" in source
    assert "Quota sync timeout after" in source
