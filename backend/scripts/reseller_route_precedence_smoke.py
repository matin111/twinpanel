from __future__ import annotations

from app.main import app


def first_endpoint(path: str, method: str) -> str | None:
    wanted = method.upper()
    for route in app.routes:
        if getattr(route, "path", None) != path:
            continue
        methods = {str(x).upper() for x in (getattr(route, "methods", None) or set())}
        if wanted not in methods:
            continue
        endpoint = getattr(route, "endpoint", None)
        return str(getattr(endpoint, "__name__", "") or "")
    return None


def main() -> None:
    expected = {
        ("/v1/reseller/plans", "GET"): "list_owned_plans",
        ("/v1/reseller/subscriptions/create", "POST"): "create_reseller_subscription",
        ("/v1/reseller/subscriptions/{subscription_id}/extend", "POST"): "extend_subscription_pool_guard",
        ("/v1/reseller/subscriptions/{subscription_id}/toggle-active", "POST"): "toggle_subscription_pool_guard",
        ("/v1/reseller/traffic/buy", "POST"): "buy_traffic_and_restore",
        ("/v1/reseller/bot-commerce/orders/{order_id}/approve", "POST"): "approve_order_owned_route",
    }

    for (path, method), endpoint_name in expected.items():
        actual = first_endpoint(path, method)
        assert actual == endpoint_name, (
            f"route precedence mismatch {method} {path}: "
            f"expected={endpoint_name} actual={actual}"
        )

    print("RESELLER_ROUTE_PRECEDENCE_OK")


if __name__ == "__main__":
    main()
