from __future__ import annotations

from typing import Any

from .routers import account_delivery, provision, tunnels


# ============================================================
# TWINPANEL UNIFIED L3 CORE V49
#
# One logical Iran <-> Exit L3 carrier owns service ingress for:
#   Cisco/OpenConnect, OpenVPN, WireGuard, L2TP/IPsec and Xray/V2Ray.
#
# Service listeners/ports stay protocol-specific, but they are no longer
# allowed to publish against a carrier before the selected L3 path exists.
#
# The old Node Agent published/FLUSHed service iptables chains before it had
# reconciled the tunnel interface. During restart/failover this could erase a
# working data plane and then fail while adding rules for an interface that was
# not ready yet. V49 changes the convergence order:
#
#   desired state
#       -> ensure/probe carrier
#       -> verify selected L3 peer is reachable
#       -> publish all service routes together
#       -> report health
#
# If the replacement carrier is not ready, existing service chains are kept.
# No half-built replacement is published.
#
# L2TP used to have a second "primary tunnel" election. V49 folds its
# UDP/500, UDP/4500 and ESP routes into the same selected service route used by
# the other protocols. This makes the selected logical tunnel the single route
# authority for the Iran/Exit pair.
# ============================================================

_runtime_applied = False
_original_make_agent = None
_original_service_routes_for_exit = None
_original_l2tp_routes_for_exit = None
_original_tunnel_access_endpoint = None


_AGENT_RECONCILE_V49 = r'''# TWINPANEL_UNIFIED_L3_AGENT_V49
def unified_l3_carrier_probe(item):
    """Verify that the desired logical L3 carrier is really usable."""

    interface = str(
        item.get("interface")
        or item.get("health_interface")
        or ""
    ).strip()

    peer_ip = str(
        item.get("peer_tunnel_ip")
        or item.get("health_peer_tunnel_ip")
        or ""
    ).strip()

    local_ip = str(
        item.get("local_address")
        or ""
    ).split("/", 1)[0].strip()

    if not interface:
        return False, "unified_l3_interface_missing", None

    if not peer_ip:
        return False, "unified_l3_peer_missing", None

    code, output = run([
        "ip",
        "link",
        "show",
        "dev",
        interface,
    ], timeout=5)

    if code != 0:
        return (
            False,
            f"unified_l3_interface_down:{interface}:{output}"[:900],
            None,
        )

    if local_ip:
        code, output = run([
            "ip",
            "-o",
            "-4",
            "addr",
            "show",
            "dev",
            interface,
        ], timeout=5)

        if code != 0 or local_ip not in output:
            return (
                False,
                f"unified_l3_local_address_missing:{interface}:{local_ip}"[:900],
                None,
            )

    code, output = run([
        "ping",
        "-I",
        interface,
        "-c",
        "3",
        "-W",
        "1",
        "-i",
        "0.25",
        peer_ip,
    ], timeout=6)

    match = re.search(
        r"=\s*[\d.]+/([\d.]+)/",
        output,
    )

    if code != 0 or not match:
        return (
            False,
            f"unified_l3_peer_unreachable:{interface}:{peer_ip}"[:900],
            None,
        )

    return (
        True,
        None,
        int(round(float(match.group(1)))),
    )


async def reconcile_tunnels(client):

    r = await http_request_retry(
        client,
        "GET",
        (
            f"{API}/v1/tunnels/"
            f"node/{NODE_ID}/desired"
        ),
        headers={
            "X-Node-Secret": SECRET,
        },
    )

    r.raise_for_status()

    items = r.json()

    # V49 phase 1: clean only obsolete legacy WireGuard interfaces, then make
    # every desired carrier converge. Service chains are intentionally left
    # untouched until the selected L3 path has been verified below.
    cleanup_ok, cleanup_error = (
        reconcile_tunnel_interfaces(
            items
        )
    )

    if not cleanup_ok:
        print(
            "[TwinPanel] stale tunnel cleanup ERROR: "
            f"{cleanup_error}",
            flush=True,
        )

    runtime_results = {}

    for item in items:

        public_key = None
        selected = None

        endpoint_ok = False
        tunnel_ok = False

        latency = None
        last_error = None

        try:

            candidates = (
                item.get(
                    "transport_candidates"
                )
                or ["wireguard"]
            )

            # Controller/systemd managed carriers expose a ready L3 interface
            # in Desired State. MTunnel belongs here as well; the old Agent
            # incorrectly fell through to legacy WireGuard configuration.
            managed_candidates = {
                "mtunnel",
                "quic_2027",
                "arq_2027",
                "kcp_2027",
                "tcp_2027",
                "ssh_tun",
                "ssh_relay",
                "backhaul",
            }

            active_name = str(
                item.get("active_transport")
                or ""
            ).strip().lower()

            if (
                active_name in managed_candidates
                or any(
                    name in managed_candidates
                    for name in candidates
                )
            ):
                selected = active_name

                if (
                    selected not in managed_candidates
                    or selected not in candidates
                ):
                    selected = next(
                        (
                            name
                            for name in candidates
                            if name in managed_candidates
                        ),
                        active_name or "ssh_tun",
                    )

                if selected == "mtunnel":
                    ok, err, latency = unified_l3_carrier_probe(
                        item
                    )
                else:
                    ok, err, latency = check_ssh_tun(
                        item
                    )

                tunnel_ok = ok
                endpoint_ok = ok
                last_error = err

            elif "wireguard" in candidates:

                public_key = ensure_keypair(
                    item["id"]
                )

                ok, err = configure_wireguard(
                    item
                )

                if ok:
                    selected = "wireguard"

                    await asyncio.sleep(
                        0.6
                    )

                    latency = ping_ms(
                        item[
                            "peer_tunnel_ip"
                        ]
                    )

                    tunnel_ok = (
                        latency is not None
                    )

                    endpoint_ok = tunnel_ok

                    if not tunnel_ok:
                        last_error = (
                            "wireguard_peer_unreachable"
                        )

                else:
                    last_error = err

            if selected is None:
                selected = (
                    candidates[0]
                    if candidates
                    else "wireguard"
                )

        except Exception as exc:

            last_error = str(
                exc
            )[:900]

        runtime_results[int(item["id"])] = {
            "public_key": public_key,
            "selected": selected,
            "endpoint_ok": endpoint_ok,
            "tunnel_ok": tunnel_ok,
            "latency": latency,
            "last_error": last_error,
        }

    # V49 phase 2: before changing any service rule, verify the actual route
    # interface and peer used by every selected service tunnel. If a failover
    # carrier is not ready yet, DO NOT call reconcile_service_routing: the old
    # working chains remain intact for the next convergence pass.
    routed_items = [
        item
        for item in items
        if (item.get("service_routes") or [])
    ]

    route_probe_errors = {}

    for item in routed_items:
        ok, error, route_latency = unified_l3_carrier_probe(
            item
        )

        if not ok:
            route_probe_errors[int(item["id"])] = (
                error or "unified_l3_not_ready"
            )
            continue

        current = runtime_results.get(
            int(item["id"])
        )

        if current is not None:
            current["endpoint_ok"] = True
            current["tunnel_ok"] = True
            if route_latency is not None:
                current["latency"] = route_latency

    if route_probe_errors:
        routing_ok = False
        routing_error = (
            "unified_l3_carrier_not_ready: "
            + "; ".join(
                f"tunnel={tunnel_id}:{error}"
                for tunnel_id, error
                in sorted(route_probe_errors.items())
            )
        )[:900]

        print(
            "[TwinPanel] unified L3 route publish DEFERRED: "
            f"{routing_error}",
            flush=True,
        )

    else:
        routing_ok, routing_error = (
            reconcile_service_routing(
                items
            )
        )

        if not routing_ok:
            print(
                "[TwinPanel] unified L3 service routing ERROR: "
                f"{routing_error}",
                flush=True,
            )
        elif routed_items:
            print(
                "[TwinPanel] UNIFIED_L3_V49 COMMITTED "
                f"routes={sum(len(x.get('service_routes') or []) for x in routed_items)}",
                flush=True,
            )

    # V49 phase 3: report after carrier + route convergence. Only the selected
    # service tunnel inherits a service-routing failure; standby members remain
    # valid failover candidates.
    for item in items:
        tunnel_id = int(item["id"])
        current = runtime_results.get(
            tunnel_id,
            {
                "public_key": None,
                "selected": None,
                "endpoint_ok": False,
                "tunnel_ok": False,
                "latency": None,
                "last_error": "runtime_result_missing",
            },
        )

        last_error = current["last_error"]

        if tunnel_id in route_probe_errors:
            current["endpoint_ok"] = False
            current["tunnel_ok"] = False
            message = route_probe_errors[tunnel_id]
            last_error = (
                f"{last_error}; {message}"
                if last_error
                else message
            )[:900]

        elif (
            (item.get("service_routes") or [])
            and not routing_ok
        ):
            message = (
                "service_routing_failed: "
                f"{routing_error or 'unknown'}"
            )
            last_error = (
                f"{last_error}; {message}"
                if last_error
                else message
            )[:900]

        await report(
            client,
            tunnel_id,
            current["public_key"],
            current["selected"],
            current["endpoint_ok"],
            current["tunnel_ok"],
            current["latency"],
            last_error,
        )
'''


def _patch_agent_source(source: str) -> str:
    if "TWINPANEL_UNIFIED_L3_AGENT_V49" in source:
        return source

    start_marker = "async def reconcile_tunnels(client):"
    end_marker = (
        "\n\n# ============================================================\n"
        "# TWINPANEL_AGENT_ORPHAN_SELF_DISABLE_V1"
    )

    start = source.find(start_marker)
    end = source.find(end_marker, start + 1)

    if start < 0 or end < 0 or end <= start:
        raise RuntimeError(
            "TwinPanel Agent source contract changed; "
            "Unified L3 V49 patch refused"
        )

    patched = (
        source[:start]
        + _AGENT_RECONCILE_V49.rstrip()
        + source[end:]
    )

    required = (
        "TWINPANEL_UNIFIED_L3_AGENT_V49",
        "unified_l3_carrier_probe",
        "UNIFIED_L3_V49 COMMITTED",
        "reconcile_service_routing",
    )

    if not all(token in patched for token in required):
        raise RuntimeError(
            "Unified L3 V49 Agent validation failed"
        )

    return patched


def _make_agent_v49(node_id: int, api_base: str) -> str:
    assert _original_make_agent is not None
    return _patch_agent_source(
        _original_make_agent(
            node_id,
            api_base,
        )
    )


def _route_key(route: dict[str, Any]) -> tuple:
    return (
        str(route.get("protocol") or "").lower(),
        str(route.get("transport") or "").lower(),
        route.get("public_port"),
        route.get("target_port"),
        str(route.get("target_ip") or ""),
    )


def _service_routes_unified_v49(
    db,
    exit_node,
    exit_tunnel_ip: str,
) -> list[dict]:
    assert _original_service_routes_for_exit is not None
    assert _original_l2tp_routes_for_exit is not None

    routes = list(
        _original_service_routes_for_exit(
            db,
            exit_node,
            exit_tunnel_ip,
        )
        or []
    )

    # L2TP/IPsec now follows the exact same selected logical L3 tunnel as all
    # other services. UDP/1701 remains protected inside IPsec; public ingress
    # needs IKE UDP/500, NAT-T UDP/4500 and ESP protocol 50.
    routes.extend(
        _original_l2tp_routes_for_exit(
            db,
            exit_node,
            exit_tunnel_ip,
        )
        or []
    )

    output: list[dict] = []
    seen: set[tuple] = set()

    for raw in routes:
        if not isinstance(raw, dict):
            continue

        route = dict(raw)
        route["core"] = "unified_l3_v49"
        key = _route_key(route)

        if key in seen:
            continue

        seen.add(key)
        output.append(route)

    return output


def _l2tp_secondary_route_disabled_v49(
    db,
    exit_node,
    exit_tunnel_ip: str,
) -> list[dict]:
    # desired_tunnels historically appended L2TP only through an independent
    # "primary" election. V49 already included it in _service_routes_for_exit,
    # so this compatibility hook intentionally returns no second copy.
    return []


def _tunnel_access_endpoint_v49(
    db,
    node,
    protocol: str,
):
    assert _original_tunnel_access_endpoint is not None

    protocol_key = str(protocol or "").strip().lower()

    if protocol_key != "l2tp":
        return _original_tunnel_access_endpoint(
            db,
            node,
            protocol,
        )

    # L2TP does not use a synthetic public service port, but its public HOST
    # must follow the same Iran ingress assignment as the other protocols.
    # The Cisco lookup is used only to reuse the established tunnel-host
    # selection policy; no Cisco listener/config is required for this lookup.
    host, _unused_port = _original_tunnel_access_endpoint(
        db,
        node,
        "cisco",
    )

    return (
        host,
        account_delivery._port(
            db,
            node.id,
            "l2tp",
        ),
    )


def apply_unified_l3_core_v49() -> None:
    global _runtime_applied
    global _original_make_agent
    global _original_service_routes_for_exit
    global _original_l2tp_routes_for_exit
    global _original_tunnel_access_endpoint

    if _runtime_applied:
        return

    # Apply last in self_hosted_runtime so we wrap the final production route
    # builders rather than bypassing any existing Xray/service extensions.
    _original_make_agent = provision.make_agent
    _original_service_routes_for_exit = (
        tunnels._service_routes_for_exit
    )
    _original_l2tp_routes_for_exit = (
        tunnels._l2tp_routes_for_exit
    )
    _original_tunnel_access_endpoint = (
        account_delivery._tunnel_access_endpoint
    )

    provision.make_agent = _make_agent_v49
    tunnels._service_routes_for_exit = (
        _service_routes_unified_v49
    )
    tunnels._l2tp_routes_for_exit = (
        _l2tp_secondary_route_disabled_v49
    )
    account_delivery._tunnel_access_endpoint = (
        _tunnel_access_endpoint_v49
    )

    _runtime_applied = True

    print(
        "TWINPANEL_UNIFIED_L3_CORE_V49_ACTIVE "
        "carrier_first=1 route_commit_after_probe=1 "
        "preserve_previous_on_failover=1 "
        "services=cisco,openvpn,wireguard,l2tp,v2ray "
        "l2tp_shared_election=1",
        flush=True,
    )
