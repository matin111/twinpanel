from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent

purchase = (ROOT / "app" / "telegram_purchase_delivery_fix_v1.py").read_text()
classic = (ROOT / "app" / "classic_node_parallel_v1.py").read_text()
init = (ROOT / "app" / "__init__.py").read_text()
payments_ui = (REPO / "components" / "payments-review-runtime.tsx").read_text()

# Telegram purchases must consume the canonical PlanProtocol list, not rebuild
# the old five-protocol boolean subset.
assert 'raw = plan.get("protocols")' in purchase
assert "normalize_protocols(raw)" in purchase
assert "PROTOCOL_TITLES.get(protocol, protocol)" in purchase
assert "FULL_PROTOCOL_KEYS" in purchase

# Every successful payment producer must collapse onto one idempotent delivery
# event regardless of whether it still emits an old event-key shape.
assert 'str(kind or "") != "payment_approved"' in purchase
assert 'f"payment-approved:order:{order_id}:"' in purchase
assert 'f"payment:{payment_id}:subscription:{subscription_id}"' in purchase

# Speed optimization is intentionally narrow: only independent Classic node
# drivers are parallel and concurrency is hard-capped. OpenVPN/L2TP stay on the
# canonical serial implementation because they have shared identity/PSK state.
assert "CLASSIC_NODE_CONCURRENCY_LIMIT = 3" in classic
assert 'frozenset({"cisco", "wireguard", "v2ray"})' in classic
assert "SessionLocal()" in classic
assert "asyncio.Semaphore(CLASSIC_NODE_CONCURRENCY_LIMIT)" in classic
assert '"openvpn"' not in classic.split("PARALLEL_CLASSIC_PROTOCOLS", 1)[1].split("_ORIGINAL_CLASSIC", 1)[0]
assert '"l2tp"' not in classic.split("PARALLEL_CLASSIC_PROTOCOLS", 1)[1].split("_ORIGINAL_CLASSIC", 1)[0]

# Admin payment review must leave the review state immediately after click and
# reconcile later; the UI may not appear stuck until a manual page refresh.
marker = "// TWINPANEL_PAYMENT_REVIEW_OPTIMISTIC_V2"
assert marker in payments_ui
ui_after_marker = payments_ui.split(marker, 1)[1]
assert ui_after_marker.index("optimistic?.();") < ui_after_marker.index("await fn();")
assert "window.setTimeout(()=>{void load(true);},1500);" in payments_ui
assert "// Roll back the optimistic state from the authoritative API" in payments_ui

assert "_install_telegram_purchase_delivery_fix_v1()" in init
assert "_install_classic_node_parallel_v1()" in init

print("telegram_purchase_delivery_speed_v1_smoke: OK")
