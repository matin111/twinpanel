from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "app" / "reseller_order_partial_provision_success_v1.py"
spec = importlib.util.spec_from_file_location(
    "reseller_order_partial_provision_success_v1_smoke",
    MODULE_PATH,
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
reconcile = module.reconcile_reseller_provision_result


warning = {
    "protocol": "cisco",
    "node_id": 2,
    "error": "node unavailable",
}
partial = {
    "ok": False,
    "created_pairs": [
        {"protocol": "cisco", "node_id": 1},
    ],
    "reused_pairs": [],
    "provision_errors": [warning],
}
accepted = reconcile(partial, {"cisco"})
assert accepted is not partial
assert accepted["ok"] is True
assert accepted["provision_errors"] == []
assert accepted["errors"] == []
assert accepted["provision_warnings"] == [warning]


missing_protocol = {
    "ok": False,
    "created_pairs": [
        {"protocol": "cisco", "node_id": 1},
    ],
    "reused_pairs": [],
    "provision_errors": [
        {
            "protocol": "openvpn",
            "node_id": 3,
            "error": "openvpn failed everywhere",
        }
    ],
}
rejected = reconcile(missing_protocol, {"cisco", "openvpn"})
assert rejected is missing_protocol
assert rejected["ok"] is False
assert rejected["provision_errors"]


xray_alias = {
    "ok": False,
    "created_pairs": [
        {"protocol": "v2ray", "node_id": 4},
    ],
    "reused_pairs": [],
    "provision_errors": [
        {
            "protocol": "v2ray",
            "node_id": 5,
            "error": "secondary node failed",
        }
    ],
}
accepted_alias = reconcile(xray_alias, {"xray"})
assert accepted_alias["ok"] is True
assert accepted_alias["provision_warnings"]


clean = {
    "ok": True,
    "created_pairs": [{"protocol": "wireguard", "node_id": 1}],
    "provision_errors": [],
}
assert reconcile(clean, {"wireguard"}) is clean

print("reseller-order-partial-provision-success: ok")
