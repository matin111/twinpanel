from pathlib import Path


def test_reseller_request_flow_contract():
    source = Path("backend/app/telegram_account_link_bot.py").read_text()

    assert 'RESELLER_REQUEST_CALLBACK = "reseller:request"' in source
    assert 'RESELLER_CONFIRM_CALLBACK = "reseller:confirm"' in source
    assert 'شرایط دریافت نمایندگی' in source
    assert 'شرایط را دارم — ثبت درخواست' in source
    assert 'subject": "درخواست نمایندگی"' in source
    assert 'ResellerRequestState.application' in source
