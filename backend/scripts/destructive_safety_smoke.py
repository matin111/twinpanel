#!/usr/bin/env python3

"""Static/runtime smoke for destructive DELETE route precedence."""

from app.routers import nodes, tunnels  # importing package registers safety shim
from app.routers import destructive_safety


def first_delete_endpoint(router, path: str):
    for route in router.routes:
        methods = set(getattr(route, "methods", set()) or set())
        if getattr(route, "path", None) == path and "DELETE" in methods:
            return getattr(route, "endpoint", None)
    raise AssertionError(f"DELETE route not found: {path}")


def main() -> None:
    node_endpoint = first_delete_endpoint(nodes.router, "/v1/nodes/{node_id}")
    tunnel_endpoint = first_delete_endpoint(tunnels.router, "/v1/tunnels/{tunnel_id}")

    assert node_endpoint is destructive_safety.safe_delete_node, (
        "safe node DELETE route is not first"
    )
    assert tunnel_endpoint is destructive_safety.safe_delete_tunnel, (
        "safe tunnel DELETE route is not first"
    )

    assert destructive_safety.SSH_PREFLIGHT_SECONDS < 30

    print("DESTRUCTIVE_SAFETY_SMOKE=OK")
    print(f"SSH_PREFLIGHT_SECONDS={destructive_safety.SSH_PREFLIGHT_SECONDS}")
    print(f"NODE_DELETE={node_endpoint.__module__}.{node_endpoint.__name__}")
    print(f"TUNNEL_DELETE={tunnel_endpoint.__module__}.{tunnel_endpoint.__name__}")


if __name__ == "__main__":
    main()
