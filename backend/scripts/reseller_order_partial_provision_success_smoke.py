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


modern_protocols = {
    "cisco",
    "openvpn",
    "wireguard",
    "l2tp",
    "v2ray",
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
    "mieru",
    "trusttunnel",
    "amneziawg",
    "sudoku",
}
modern_partial = {
    "ok": False,
    "credentials": [
        {"protocol": protocol, "items": [{"node": f"ok-{protocol}"}]}
        for protocol in sorted(modern_protocols)
    ],
    "errors": [
        {
            "protocol": "v2ray",
            "node": "secondary-exit",
            "error": "listener verification failed",
        },
        {
            "protocol": "wireguard",
            "node": "secondary-exit",
            "error": "node timeout",
        },
    ],
}
accepted_modern = reconcile(modern_partial, modern_protocols)
assert accepted_modern is not modern_partial
assert accepted_modern["ok"] is True
assert accepted_modern["errors"] == []
assert accepted_modern["provision_errors"] == []
assert accepted_modern["provision_warnings"] == modern_partial["errors"]


modern_missing = {
    **modern_partial,
    "credentials": [
        row
        for row in modern_partial["credentials"]
        if row["protocol"] != "wireguard"
    ],
}
rejected_modern = reconcile(modern_missing, modern_protocols)
assert rejected_modern is modern_missing
assert rejected_modern["ok"] is False
assert rejected_modern["errors"]


modern_empty_items = {
    "ok": False,
    "credentials": [
        {"protocol": "v2ray", "items": []},
    ],
    "errors": [
        {"protocol": "v2ray", "node": "all", "error": "no usable config"},
    ],
}
assert reconcile(modern_empty_items, {"v2ray"}) is modern_empty_items


clean = {
    "ok": True,
    "created_pairs": [{"protocol": "wireguard", "node_id": 1}],
    "provision_errors": [],
}
assert reconcile(clean, {"wireguard"}) is clean

print("reseller-order-partial-provision-success: ok")
