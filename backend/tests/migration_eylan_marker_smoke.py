from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "app" / "routers" / "migration_center_v2.py"


def test_eylan_marker_uses_encrypted_non_null_payload() -> None:
    text = ROUTER.read_text(encoding="utf-8")
    assert "from ..services.migration_import_v2 import _enc_payload, import_record, legacy_payload" in text
    assert "preserved_payload_encrypted=_enc_payload(" in text
    assert '"credential_policy": "twinpanel_generated_protocol_credentials"' in text
    assert "preserved_payload_encrypted=None" not in text


if __name__ == "__main__":
    test_eylan_marker_uses_encrypted_non_null_payload()
    print("migration_eylan_marker_smoke: 1 passed")
