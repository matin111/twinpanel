from __future__ import annotations

from pathlib import Path
import runpy


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "backend" / "app" / "routers" / "public_connection_render_cache_v26.py"
HUB = ROOT / "backend" / "app" / "routers" / "public_connection_hub_live_v5.py"

v26 = runpy.run_path(str(MODULE))
install = v26["install_public_payload_render_cache_v26"]
render_cache = v26["public_connection_render_cache_v26"]


class FakeDB:
    pass


class FakeSub:
    def __init__(self, subscription_id: int):
        self.id = subscription_id


class FakeAccountDelivery:
    def __init__(self):
        self.calls = 0

        def public_payload(db, sub):
            self.calls += 1
            return {
                "subscription_id": sub.id,
                "credentials": [
                    {
                        "protocol": "wireguard",
                        "items": [{"qr": f"qr-{self.calls}"}],
                    }
                ],
            }

        self._public_payload = public_payload


module = FakeAccountDelivery()
install(module)
wrapped_once = module._public_payload
install(module)
assert module._public_payload is wrapped_once, "V26 install must be idempotent"

# Outside a Public Connect render the wrapper is intentionally inert.
db = FakeDB()
sub = FakeSub(17)
module._public_payload(db, sub)
module._public_payload(db, sub)
assert module.calls == 2, module.calls


@render_cache
def render_same_subscription():
    first = module._public_payload(db, sub)
    # Simulate a legacy renderer mutating its private payload copy.
    first["credentials"][0]["items"][0]["qr"] = "mutated"
    second = module._public_payload(db, sub)
    return first, second


first, second = render_same_subscription()
assert module.calls == 3, module.calls
assert first["credentials"][0]["items"][0]["qr"] == "mutated"
assert second["credentials"][0]["items"][0]["qr"] == "qr-3"

# Cache lifetime is one render only; a later request must rebuild fresh data.
third, fourth = render_same_subscription()
assert module.calls == 4, module.calls
assert third["credentials"][0]["items"][0]["qr"] == "mutated"
assert fourth["credentials"][0]["items"][0]["qr"] == "qr-4"

# Different subscriptions never alias inside the same request.
sub2 = FakeSub(18)


@render_cache
def render_two_subscriptions():
    a = module._public_payload(db, sub)
    b = module._public_payload(db, sub2)
    a_again = module._public_payload(db, sub)
    b_again = module._public_payload(db, sub2)
    return a, b, a_again, b_again


render_two_subscriptions()
assert module.calls == 6, module.calls

hub = HUB.read_text(encoding="utf-8")
assert "install_public_payload_render_cache_v26" in hub
assert "public_connection_render_cache_v26" in hub
assert "@public_connection_render_cache_v26" in hub
assert hub.index("install_public_payload_render_cache_v26") < hub.index(
    "public_connection_modern_delivery_v13"
), "V26 must patch Account Delivery before V13/V14/V16 import _public_payload"

print("V26 Public Connect render cache smoke: PASS")
