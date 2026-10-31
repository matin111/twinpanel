from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_admin_fast_create_is_not_fire_and_forget() -> None:
    source = _source("backend/app/routers/subscription_create_fast_v1.py")

    assert "asyncio.create_task" not in source
    assert "_TASKS" not in source
    assert "await admin_create_v2" in source
    assert '"provisioning_complete"' in source


def test_reseller_create_routes_require_provisioning_completion() -> None:
    source = _source("backend/app/routers/reseller_owned_plans.py")

    assert "async def _complete_reseller_provisioning" in source
    assert "await provision_account_v1" in source
    assert "ProtocolCredential.is_active" in source
    assert "ProtocolCredential.config_text_encrypted" in source
    assert "SubscriptionStatus.SUSPENDED" in source
    assert 'command_type="revoke_subscription"' in source

    assert "async def create_reseller_subscription" in source
    assert "async def create_reseller_manual_subscription" in source
    assert source.count("return await _complete_reseller_provisioning(") == 2
