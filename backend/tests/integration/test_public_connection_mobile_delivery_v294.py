from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_mobile_v17_is_compact_protocol_aware_and_desktop_safe():
    source = _text("backend/app/routers/public_connection_mobile_protocols_v17.py")

    assert "TWINPANEL_MOBILE_ADAPTIVE_DELIVERY_V294" in source
    assert "@media(max-width:720px)" in source
    assert "@media(max-width:430px)" in source
    assert "credentialFirst=new Set(['cisco','l2tp'])" in source
    assert "v17-credential-first" in source
    assert "v17-config-first" in source
    assert "v17-advanced-action" in source
    assert "bindAccordion" in source
    assert "if(cards.length===1)cards[0].open=true" in source
    assert "if(index===0)card.open=true" not in source
    assert "body.dataset.tpMobileAdaptive='v294'" in source


def test_mobile_v18_only_advertises_live_delivery_eligible_servers():
    source = _text("backend/app/routers/public_connection_mobile_server_inventory_v18.py")

    assert "TWINPANEL_MOBILE_ELIGIBLE_SERVER_INVENTORY_V294" in source
    assert "Node.show_to_users.is_(True)" in source
    assert "Node.retired_at.is_(None)" in source
    assert "_enum_value(cfg.status) != \"online\"" in source
    assert "_delivery_item_is_usable(db, protocol, {\"node_id\": node_id})" in source
    assert '"eligible_node_ids": sorted(eligible.get(protocol, set()))' in source
    assert '"ready_node_ids": sorted(ready.get(protocol, set()))' in source
    assert '"delivery_policy": "eligible-live-topology-v294"' in source

    # The phone UI consumes the protocol-specific eligibility set. It must not
    # append every global Exit as a fake/pending server for every protocol.
    assert "eligibleNodes(inventory,key)" in source
    assert "protocol.eligible_node_ids" in source
    assert "if(!eligible.has(String(row.dataset.nodeId||'')))row.remove()" in source
    assert "document.body.dataset.tpMobileEligibleInventory='v294'" in source
