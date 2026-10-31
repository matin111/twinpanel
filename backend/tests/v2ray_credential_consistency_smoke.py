from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FACTORY = ROOT / "backend" / "app" / "services" / "subscription_factory.py"
DELIVERY = ROOT / "backend" / "app" / "routers" / "modern_account_delivery_v1.py"


def test_v2ray_placeholder_is_not_active_before_config_exists() -> None:
    source = FACTORY.read_text(encoding="utf-8")
    assert 'is_active=(protocol != "v2ray")' in source


def test_classic_provisioning_activates_only_after_items_exist() -> None:
    source = DELIVERY.read_text(encoding="utf-8")
    block_start = source.index("async def _provision_classic_protocol(")
    block_end = source.index("\n\nasync def _provision_account_v1_locked(", block_start)
    block = source[block_start:block_end]
    assert "if items:" in block
    assert "cred.config_text_encrypted = ad._enc(items)" in block
    assert "cred.is_active = True" in block
    assert block.index("if items:") < block.index("cred.is_active = True")


if __name__ == "__main__":
    test_v2ray_placeholder_is_not_active_before_config_exists()
    test_classic_provisioning_activates_only_after_items_exist()
    print("v2ray_credential_consistency_smoke: 2 passed")
