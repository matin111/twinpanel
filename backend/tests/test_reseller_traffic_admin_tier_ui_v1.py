"""Reseller recharge admin must send the tier already required by the backend API."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
UI=(ROOT.parent/"components"/"admin-reseller-traffic-plans.tsx").read_text(encoding="utf-8")
API=(ROOT/"app"/"routers"/"resellers.py").read_text(encoding="utf-8")
PORTAL=(ROOT/"app"/"routers"/"reseller_portal.py").read_text(encoding="utf-8")
POLICY=(ROOT/"app"/"reseller_tier_policy.py").read_text(encoding="utf-8")

def test_recharge_create_update_send_required_type():
    assert "reseller_tier: str" in API
    assert "const payload={reseller_tier:draft.reseller_tier" in UI
    assert 'reseller_tier:isTier(row.reseller_tier)?row.reseller_tier:"premium_static_ip"' in UI

def test_two_reseller_categories_have_distinct_admin_pricing():
    assert 'value:"economic_v2ray",fa:"ویتوری"' in UI
    assert 'value:"premium_static_ip",fa:"ویژه"' in UI
    assert "const [tierFilter,setTierFilter]" in UI
    assert 'pick("نوع نمایندگی","Reseller type")' in UI
    assert "price_toman:price" in UI

def test_reseller_can_only_purchase_own_tier():
    assert "ResellerTrafficPackage.reseller_tier == reseller_tier(reseller)" in PORTAL
    assert "def check_package_tier(" in POLICY
    assert 'TIER_LABELS[tier]' in POLICY

def test_legacy_packages_remain_premium():
    assert 'reseller_tier:"premium_static_ip"' in UI
    assert '"premium_static_ip")===tierFilter' in UI
