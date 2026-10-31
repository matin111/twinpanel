from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "app" / "routers" / "subscription_admin_v2.py"
FRONTEND = ROOT.parent / "components" / "admin-subscription-live-table.tsx"


def test_admin_v2_subscription_list_uses_bulk_context() -> None:
    text = PATH.read_text(encoding="utf-8")
    assert "def _bulk_admin_list_context(" in text
    assert "def _enriched_payload_from_context(" in text
    assert "context = _bulk_admin_list_context(db, rows)" in text
    assert "return [_enriched_payload_from_context(sub, context) for sub in rows]" in text


def test_admin_v2_list_does_not_use_per_row_enrichment() -> None:
    text = PATH.read_text(encoding="utf-8")
    list_block = text.split('@router.get("/admin-list-v2")', 1)[1].split('@router.post("/admin-create-v2")', 1)[0]
    assert "_enriched_payload(db, sub)" not in list_block
    assert "_bulk_admin_list_context(db, rows)" in list_block


def test_live_status_polling_is_single_flight_and_throttled() -> None:
    text = FRONTEND.read_text(encoding="utf-8")
    assert "let inFlight=false;" in text
    assert 'document.visibilityState==="hidden"' in text
    assert "signal:controller.signal" in text
    assert "controller?.abort();" in text
    assert "15000" in text
    assert "5000" not in text


if __name__ == "__main__":
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print("subscriptions_bulk_smoke: passed")
