from __future__ import annotations


def test_duplicate_email_repair_rewrites_merge_contract() -> None:
    from app import xray_duplicate_email_repair_v1
    from app import xray_modern_runtime

    xray_duplicate_email_repair_v1.install()
    script = xray_modern_runtime._merge_clients_script()

    assert 'raise RuntimeError("Xray duplicate email conflict")' not in script
    assert "email_to_id[email] != client_id" in script
    assert "continue" in script
    assert "clients_by_id[client_id] = item" in script
    assert "email_to_id[email] = client_id" in script
