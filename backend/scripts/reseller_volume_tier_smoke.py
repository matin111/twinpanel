"""Contract and pure behavior smoke for two volume-only reseller tiers.

Does not connect to database or perform any purchase / create / charge actions.
"""
from pathlib import Path
from types import SimpleNamespace
import ast

root = Path(__file__).resolve().parents[1]
app = root / "app"
sources = {
    "model": app / "models_reseller.py",
    "policy": app / "reseller_tier_policy.py",
    "admin": app / "routers/reseller_admin_v2.py",
    "admin_legacy": app / "routers/resellers.py",
    "traffic_list": app / "routers/reseller_traffic_admin_v2.py",
    "traffic_buy": app / "routers/reseller_traffic_purchase_v3.py",
    "traffic_portal": app / "routers/reseller_portal.py",
    "owned": app / "reseller_owned_plans.py",
    "owned_api": app / "routers/reseller_owned_plans.py",
    "manual": app / "reseller_manual_subscriptions.py",
    "sale": app / "routers/reseller_sale_v2.py",
    "servers": app / "routers/reseller_subscription_volume_v2.py",
    "ui_admin": root.parent / "components/admin-resellers-legacy-v3.tsx",
    "ui_alt": root.parent / "components/admin-parity-runtime.tsx",
    "ui_plans": root.parent / "components/reseller-owned-plans.tsx",
}
text = {k:v.read_text(encoding="utf-8") for k,v in sources.items()}
for key in sources:
    if not key.startswith("ui_"):
        ast.parse(text[key], filename=str(sources[key]))

for term in (
    "ADD COLUMN IF NOT EXISTS reseller_tier",
    "reseller_traffic_packages",
    "'premium_static_ip'",
):
    assert term in text["model"], term
assert 'reseller_tier: str' in text["admin"]
assert 'reseller_tier: str' in text["admin_legacy"]
assert '"reseller_tier": valid_tier(reseller.reseller_tier)' in text["admin"]
assert "reseller_tier=tier" in text["admin"]
assert "tier_entitlements(db, tier)" in text["admin_legacy"]
assert "check_package_tier(reseller, package)" in text["traffic_buy"]
assert "check_package_tier(reseller, package)" in text["traffic_portal"]
assert "ResellerTrafficPackage.reseller_tier == reseller_tier(reseller)" in text["traffic_portal"]
assert 'reseller_tier: str' in text["admin_legacy"]
assert 'valid_tier(payload.reseller_tier)' in text["admin_legacy"]
assert '"reseller_tier": valid_tier(row.reseller_tier)' in text["traffic_list"]
assert "allowed_nodes(db, reseller, node_ids)" in text["owned"]
assert "allowed_nodes(db, reseller, node_ids)" in text["manual"]
assert "permitted_ids = set(tier_entitlements(db, reseller_tier(reseller))" in text["sale"]
assert "int(node.id) in permitted_ids" in text["sale"]
assert "assert_plan_tier(db, reseller, int(plan.id))" in text["sale"]
assert "tier_entitlements(db, reseller_tier(reseller))" in text["servers"]
assert "reseller_tier" in text["ui_admin"] and "reseller_tier" in text["ui_alt"]
assert "packageDraft.reseller_tier" in text["ui_admin"]
assert "allowedProtocols.has(protocol)" in text["ui_plans"]

class HTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code

policy_tree = ast.parse(text["policy"])
function_names = {
    "valid_tier", "reseller_tier", "check_package_tier",
    "allowed_nodes", "allowed_protocols",
}
functions = [
    node for node in policy_tree.body
    if isinstance(node, ast.FunctionDef) and node.name in function_names
]
class StubDB: pass
def tier_entitlements(db, tier):
    return {
        "protocols": ["v2ray", "hysteria2"] if tier == "economic_v2ray" else ["openvpn", "cisco", "v2ray"],
        "node_ids": [7] if tier == "economic_v2ray" else [7,8,9],
    }
env = {
    "HTTPException": HTTPException,
    "Reseller": object, "ResellerTrafficPackage": object,
    "Session": object, "SimpleNamespace": SimpleNamespace,
    "tier_entitlements": tier_entitlements,
    "normalize_protocols": lambda values: list(dict.fromkeys(str(v).lower() for v in values)),
    "ECONOMIC": "economic_v2ray", "PREMIUM": "premium_static_ip",
    "TIERS": ("economic_v2ray", "premium_static_ip"),
}
exec(compile(ast.Module(body=functions, type_ignores=[]), "reseller_tier_policy", "exec"), env)
e = SimpleNamespace(reseller_tier="economic_v2ray")
p = SimpleNamespace(reseller_tier="premium_static_ip")
assert env["allowed_protocols"](StubDB(), e, ["v2ray"]) == ["v2ray"]
assert env["allowed_nodes"](StubDB(), e, []) == [7]
assert env["allowed_protocols"](StubDB(), p, ["openvpn"]) == ["openvpn"]
env["check_package_tier"](e, SimpleNamespace(reseller_tier="economic_v2ray"))
for test in (
    lambda: env["allowed_protocols"](StubDB(), e, ["openvpn"]),
    lambda: env["allowed_nodes"](StubDB(), e, [9]),
    lambda: env["check_package_tier"](e, SimpleNamespace(reseller_tier="premium_static_ip")),
    lambda: env["valid_tier"]("unauthorized"),
):
    try:
        test()
        raise AssertionError("cross-tier request was allowed")
    except HTTPException as exc:
        assert exc.status_code in (403, 422)

print("VOLUME_RESELLER_TWO_TIER_ACCESS=PASS")
