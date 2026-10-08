from pydantic import BaseModel
# TWINPANEL_SINGLE_WRITER_ROUTE_STABILITY_V5
# TWINPANEL_AUTO_TUNNEL_CORE_V3
import asyncio
import fcntl
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal, get_db
from ..deps import require_admin
from ..models import Node, NodeProtocolConfig, NodeType, Tunnel, TunnelPeerState, TunnelStatus, TunnelTransport, CleanupJob
from ..schemas import TunnelCreate, TunnelOut, TunnelPeerReportIn, TunnelUpdate
from .provision import (
    ssh_connect_saved,
    cmd,
    ufw_allow,
    _install_or_upgrade_agent,
    _install_tunnel_fabric_base,
)
from ..ssh_tunnel import (
    provision_ssh_tunnel,
    cleanup_ssh_tunnel,
    ssh_tunnel_interface,
    ssh_tunnel_health_meta,
)

router = APIRouter(prefix="/v1/tunnels", tags=["tunnels"])


# TWINPANEL_MANUAL_TRANSPORT_SCHEMA_V2
class TunnelTransportModeIn(BaseModel):
    mode: str
    transport: str | None = None



# TWINPANEL_MANAGED_PREFLIGHT_PAIR_V1
async def _tp_managed_preflight_node(
    node: Node,
    db: Session,
) -> dict:
    from ..managed_preflight import (
        preflight_managed_artifacts_on_conn,
    )

    conn = await ssh_connect_saved(
        node,
        db,
    )

    try:
        return await preflight_managed_artifacts_on_conn(
            conn,
            db,
            node.id,
            cleanup=True,
        )

    finally:
        conn.close()
        await conn.wait_closed()


async def _tp_managed_preflight_pair(
    iran: Node,
    exit_node: Node,
    db: Session,
) -> dict:
    iran_result = await _tp_managed_preflight_node(
        iran,
        db,
    )

    exit_result = await _tp_managed_preflight_node(
        exit_node,
        db,
    )

    return {
        "iran": iran_result,
        "exit": exit_result,
    }



def _require_node_secret(x_node_secret: str | None) -> None:
    if x_node_secret != settings.node_agent_shared_secret:
        raise HTTPException(status_code=401, detail="Invalid node secret")


def _interface_name(tunnel_id: int) -> str:
    return f"mwg{tunnel_id}"[:15]


from ..ssh_relay import relay_desired_meta
from ..lifecycle_cleanup import cleanup_tunnel_runtime

# TWINPANEL_TRANSPORT_CORE_V2

def _effective_transport(
    tunnel: Tunnel,
) -> str:
    """
    Physical transport currently responsible for the data plane.

    active_transport is authoritative.
    preferred_transport is only fallback.
    legacy transport is compatibility fallback.
    """
    return str(
        getattr(
            tunnel,
            "active_transport",
            None,
        )
        or getattr(
            tunnel,
            "preferred_transport",
            None,
        )
        or getattr(
            tunnel,
            "transport",
            None,
        )
        or "ssh_tun"
    ).strip().lower()


def _is_ssh_tun(
    tunnel: Tunnel,
) -> bool:
    return (
        _effective_transport(tunnel)
        == "ssh_tun"
    )


def _health_interface_name(
    tunnel: Tunnel,
) -> str:

    transport = _effective_transport(
        tunnel
    )

    if transport == "mtunnel":
        return f"mtun{int(tunnel.id)}"[:15]

    if transport == "ssh_tun":
        return ssh_tunnel_interface(
            tunnel
        )

    if transport == "ssh_relay":
        # Relay-specific desired metadata may override
        # this later in desired-state generation.
        return ssh_tunnel_interface(
            tunnel
        )

    if transport == "backhaul":
        try:
            runtime = _backhaul_runtime_values(
                int(tunnel.id)
            )
            return str(
                runtime.get("interface")
                or _interface_name(tunnel.id)
            )
        except Exception:
            return _interface_name(
                tunnel.id
            )

    return _interface_name(
        tunnel.id
    )


def _data_interface_name(
    tunnel: Tunnel,
) -> str:

    transport = _effective_transport(
        tunnel
    )

    if transport == "mtunnel":
        return f"mtun{int(tunnel.id)}"[:15]

    if transport == "backhaul":
        try:
            runtime = _backhaul_runtime_values(
                int(tunnel.id)
            )
            return str(
                runtime.get("interface")
                or _interface_name(tunnel.id)
            )
        except Exception:
            return _interface_name(
                tunnel.id
            )

    if transport == "ssh_tun":
        if int(tunnel.id) == 30:
            return _interface_name(
                tunnel.id
            )

        return ssh_tunnel_interface(
            tunnel
        )

    return _interface_name(
        tunnel.id
    )


def _ssh_tun_health_meta(
    tunnel: Tunnel,
    node_id: int,
) -> tuple[str | None, str | None]:
    if not _is_ssh_tun(tunnel):
        return None, None

    return ssh_tunnel_health_meta(
        tunnel,
        node_id,
    )


# TWINPANEL_TUNNEL_WG_AUTO_PORT_ROTATION_V1
def _wg_port(tunnel_id: int) -> int:
    """Default deterministic WireGuard port for a tunnel."""
    return 52000 + (int(tunnel_id) % 1000)


def _tunnel_wg_port(tunnel: Tunnel) -> int:
    """Return the persisted port, falling back to the legacy default."""
    value = getattr(tunnel, "wireguard_port", None)

    if value is not None:
        try:
            value = int(value)
            if 1024 <= value <= 65535:
                return value
        except (TypeError, ValueError):
            pass

    return _wg_port(tunnel.id)


def _next_tunnel_wg_port(tunnel: Tunnel) -> int:
    """
    Rotate through independent high UDP port ranges while retaining
    the tunnel suffix.

    Example for tunnel 2:
        52002 -> 53002 -> 54002 -> ... -> 59002 -> 52002
    """
    current = _tunnel_wg_port(tunnel)
    suffix = int(tunnel.id) % 1000

    base = current - suffix

    if base < 52000 or base > 59000 or base % 1000 != 0:
        base = 52000

    next_base = base + 1000

    if next_base > 59000:
        next_base = 52000

    return next_base + suffix


def _tunnel_addresses(tunnel_id: int) -> tuple[str, str, str]:
    value = max(int(tunnel_id), 1)
    second = 64 + ((value // 16384) % 64)
    third = (value // 64) % 256
    block = (value % 64) * 4
    network = f"10.{second}.{third}.{block}/30"
    iran_ip = f"10.{second}.{third}.{block + 1}/30"
    exit_ip = f"10.{second}.{third}.{block + 2}/30"
    return network, iran_ip, exit_ip


# TWINPANEL_SERVICE_ROUTING_V1

_SERVICE_PUBLIC_PORT_BASE = {
    "cisco": 20000,
    "openvpn": 21000,
    "wireguard": 22000,
    "v2ray": 23000,
}

_SERVICE_DEFAULT_PORT = {
    "cisco": 443,
    "openvpn": 1194,
    "wireguard": 51820,
    "v2ray": 8443,
}

_SERVICE_DEFAULT_TRANSPORT = {
    "cisco": "tcp+udp",
    "openvpn": "udp",
    "wireguard": "udp",
    "v2ray": "tcp",
}

_SERVICE_CLIENT_SUBNET = {
    "cisco": "10.91.0.0/24",
    "openvpn": "10.92.0.0/24",
    "wireguard": "10.93.0.0/24",
    "v2ray": None,
}


def _service_public_port(exit_node_id: int, protocol: str) -> int:
    """
    Node 4:
      Cisco     20004
      OpenVPN   21004
      WireGuard 22004
      Xray      23004

    این نسخه برای حداکثر 999 Exit طراحی شده است.
    """

    node_id = int(exit_node_id)

    if node_id < 1 or node_id > 999:
        raise ValueError(
            "Service routing currently supports exit node ids 1..999"
        )

    return _SERVICE_PUBLIC_PORT_BASE[protocol] + node_id


# TWINPANEL_SERVICE_ROUTES_V2
def _service_routes_for_exit(
    db: Session,
    exit_node: Node,
    exit_tunnel_ip: str,
) -> list[dict]:

    configs = {
        item.protocol: item
        for item in db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id
            == exit_node.id
        )
        .all()
    }

    output: list[dict] = []

    for protocol in (
        "cisco",
        "openvpn",
        "wireguard",
        "v2ray",
    ):
        cfg=configs.get(protocol)

        if (
            not cfg
            or str(
                cfg.status or ""
            ).lower() != "online"
        ):
            continue

        target_port=int(
            cfg.port
            or _SERVICE_DEFAULT_PORT[
                protocol
            ]
        )

        transport=str(
            cfg.transport
            or _SERVICE_DEFAULT_TRANSPORT[
                protocol
            ]
        ).lower()

        if protocol == "cisco":
            # CSTP TCP + DTLS UDP
            transport="tcp+udp"

        elif protocol == "wireguard":
            transport="udp"

        elif protocol == "v2ray":
            transport="tcp"

        elif protocol == "openvpn":
            if transport not in {
                "tcp",
                "udp",
            }:
                transport="udp"

        output.append({
            "protocol":
                protocol,

            "exit_node_id":
                int(exit_node.id),

            "public_port":
                _service_public_port(
                    exit_node.id,
                    protocol,
                ),

            "target_ip":
                exit_tunnel_ip,

            "target_port":
                target_port,

            "transport":
                transport,

            "client_subnet":
                _SERVICE_CLIENT_SUBNET[
                    protocol
                ],
        })

    return output



# TWINPANEL_L2TP_PRIMARY_ROUTING_V1
_L2TP_CLIENT_SUBNET = "10.94.0.0/24"
_L2TP_PUBLIC_PORTS = (500, 4500)


# TWINPANEL_L2TP_ESP_ROUTING_V2
def _l2tp_routes_for_exit(
    db: Session,
    exit_node: Node,
    exit_tunnel_ip: str,
) -> list[dict]:

    cfg=(
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id
            == exit_node.id,

            NodeProtocolConfig.protocol
            == "l2tp",
        )
        .first()
    )

    if (
        not bool(exit_node.enable_l2tp)
        or not cfg
        or str(
            cfg.status or ""
        ).lower() != "online"
    ):
        return []

    output=[
        {
            "protocol":
                "l2tp",

            "exit_node_id":
                int(exit_node.id),

            "public_port":
                port,

            "target_ip":
                exit_tunnel_ip,

            "target_port":
                port,

            "transport":
                "udp",

            "client_subnet":
                _L2TP_CLIENT_SUBNET,
        }
        for port in _L2TP_PUBLIC_PORTS
    ]

    # IPsec ESP = IP protocol 50.
    # Port fields intentionally unused by Agent V62.
    output.append({
        "protocol":
            "l2tp",

        "exit_node_id":
            int(exit_node.id),

        "public_port":
            None,

        "target_ip":
            exit_tunnel_ip,

        "target_port":
            None,

        "transport":
            "esp",

        "client_subnet":
            _L2TP_CLIENT_SUBNET,
    })

    return output



def _l2tp_primary_tunnel_id(
    db: Session,
    iran_node_id: int,
) -> int | None:

    tunnels = (
        db.query(Tunnel)
        .filter(
            Tunnel.iran_node_id == iran_node_id,
            Tunnel.is_active.is_(True),
            Tunnel.status == TunnelStatus.ONLINE,
        )
        .order_by(
            Tunnel.priority.asc(),
            Tunnel.id.asc(),
        )
        .all()
    )

    for tunnel in tunnels:
        exit_node = db.get(
            Node,
            tunnel.exit_node_id,
        )

        if not exit_node:
            continue

        cfg = (
            db.query(NodeProtocolConfig)
            .filter(
                NodeProtocolConfig.node_id == exit_node.id,
                NodeProtocolConfig.protocol == "l2tp",
            )
            .first()
        )

        if (
            bool(exit_node.enable_l2tp)
            and cfg
            and str(cfg.status or "").lower() == "online"
        ):
            return int(tunnel.id)

    return None


# TWINPANEL_TUNNEL_PROVISION_V1
async def _prepare_tunnel_node(node: Node, db: Session, wg_port: int):
    conn = await ssh_connect_saved(node, db)
    try:
        await cmd(conn, ("if ! command -v wg >/dev/null 2>&1; then " "export DEBIAN_FRONTEND=noninteractive; apt-get update -y >/dev/null && " "apt-get install -y wireguard-tools kmod iproute2 iptables iputils-ping >/dev/null; fi"), timeout=900)
        await cmd(conn, "modprobe wireguard >/dev/null 2>&1 || true", check=False)
        await cmd(conn, "printf 'net.ipv4.ip_forward=1\n' > /etc/sysctl.d/99-twinpanel.conf && sysctl -p /etc/sysctl.d/99-twinpanel.conf >/dev/null")
        # TWINPANEL_WG_ASYMMETRIC_FIREWALL_V1
        # Iran listens on base+1 while Exit listens on base.
        # Open both so either role can receive WireGuard packets.
        await ufw_allow(conn, wg_port, "udp")
        await ufw_allow(conn, wg_port + 1, "udp")
        await _install_or_upgrade_agent(conn, node.id, api_base="https://api.movilineapp.com")
        state = (await conn.run("systemctl is-active twinpanel-agent.service", check=False)).stdout.strip()
        if state != "active":
            raise RuntimeError(f"Agent نود {node.name} فعال نیست: {state or 'unknown'}")
    finally:
        conn.close()
        await conn.wait_closed()

async def _wait_tunnel_online(db: Session, tunnel_id: int):
    # TWINPANEL_TUNNEL_AUTO_SELF_HEAL_V1

    async def wait_online(rounds: int = 20):
        for _ in range(rounds):
            await asyncio.sleep(2)
            db.expire_all()

            current = db.get(
                Tunnel,
                tunnel_id,
            )

            if (
                current
                and current.status == TunnelStatus.ONLINE
            ):
                return current

        return None

    # First normal Agent/reconcile window.
    item = await wait_online()

    if item:
        return item

    db.expire_all()

    tunnel = db.get(
        Tunnel,
        tunnel_id,
    )

    if not tunnel:
        raise HTTPException(
            status_code=404,
            detail="تونل پیدا نشد",
        )

    iran = db.get(
        Node,
        tunnel.iran_node_id,
    )

    exit_node = db.get(
        Node,
        tunnel.exit_node_id,
    )

    if not iran or not exit_node:
        tunnel.status = TunnelStatus.OFFLINE
        db.commit()

        raise HTTPException(
            status_code=502,
            detail="نودهای تونل برای تعمیر خودکار در دسترس نیستند",
        )

    # Reset runtime reports so only fresh Agent reports
    # can make the tunnel ONLINE after repair.
    states = (
        db.query(TunnelPeerState)
        .filter(
            TunnelPeerState.tunnel_id == tunnel.id
        )
        .all()
    )

    for state in states:
        state.endpoint_reachable = False
        state.tunnel_reachable = False
        state.latency_ms = None
        state.last_error = "auto_retry_pending"
        state.updated_at = datetime.utcnow()

    tunnel.status = TunnelStatus.OFFLINE
    tunnel.latency_ms = None

    db.commit()

    wg_port = _tunnel_wg_port(tunnel)

    repair_errors = []

    # One automatic repair attempt on both real nodes.
    for node in (iran, exit_node):
        try:
            await _prepare_tunnel_node(
                node,
                db,
                wg_port,
            )
        except Exception as exc:
            repair_errors.append(
                f"node {node.id}: {str(exc)[:300]}"
            )

    if repair_errors:
        db.expire_all()

        tunnel = db.get(
            Tunnel,
            tunnel_id,
        )

        if tunnel:
            tunnel.status = TunnelStatus.OFFLINE
            db.commit()

        raise HTTPException(
            status_code=502,
            detail=(
                "تعمیر خودکار تونل ناموفق بود: "
                + " | ".join(repair_errors)
            ),
        )

    # Give upgraded/restarted Agents a second full
    # reconcile + WireGuard handshake window.
    item = await wait_online()

    if item:
        return item

    db.expire_all()

    tunnel = db.get(
        Tunnel,
        tunnel_id,
    )

    if not tunnel:
        raise HTTPException(
            status_code=404,
            detail="تونل پیدا نشد",
        )

    states = (
        db.query(TunnelPeerState)
        .filter(
            TunnelPeerState.tunnel_id == tunnel.id
        )
        .order_by(
            TunnelPeerState.node_id.asc()
        )
        .all()
    )

    diagnostics = []

    for state in states:
        diagnostics.append(
            (
                f"node={state.node_id}, "
                f"endpoint={state.endpoint_reachable}, "
                f"tunnel={state.tunnel_reachable}, "
                f"error={state.last_error or 'none'}"
            )
        )

    raise HTTPException(
        status_code=504,
        detail=(
            "تونل پس از تعمیر خودکار آنلاین نشد"
            + (
                ": " + " | ".join(diagnostics)
                if diagnostics
                else ""
            )
        ),
    )


# TWINPANEL_TUNNEL_WATCHDOG_V1
#
# Central 24/7 tunnel health watchdog.
#
# Node Agents normally report approximately every 15 seconds.
# A peer becomes stale only after multiple missed reports.
#
_TUNNEL_WATCHDOG_INTERVAL_SECONDS = 15
_TUNNEL_REPORT_STALE_SECONDS = 60
# TWINPANEL_TUNNEL_WATCHDOG_STABLE_V43
# TWINPANEL_TUNNEL_WATCHDOG_SAFE_MODE_V45
# Temporary: status monitoring stays active, destructive
# repair/port-rotation is disabled until stable recovery is verified.
_TUNNEL_FAILURE_THRESHOLD = 999999
_TUNNEL_REPAIR_COOLDOWN_SECONDS = 600

_tunnel_watchdog_failures: dict[int, int] = {}
_tunnel_watchdog_last_repair: dict[int, datetime] = {}
_tunnel_watchdog_repair_lock = asyncio.Lock()


def _watchdog_state_age_seconds(
    state: TunnelPeerState | None,
    now: datetime,
) -> float | None:
    if not state or not state.updated_at:
        return None

    return max(
        0.0,
        (now - state.updated_at).total_seconds(),
    )


def _watchdog_state_usable(
    state: TunnelPeerState | None,
    now: datetime,
) -> bool:
    age = _watchdog_state_age_seconds(
        state,
        now,
    )

    return bool(
        state
        and age is not None
        and age <= _TUNNEL_REPORT_STALE_SECONDS
        and state.tunnel_reachable
        and not state.last_error
    )


def _watchdog_tunnel_fully_usable(
    db: Session,
    tunnel: Tunnel,
    now: datetime,
) -> bool:
    states = (
        db.query(TunnelPeerState)
        .filter(
            TunnelPeerState.tunnel_id == tunnel.id
        )
        .all()
    )

    by_node = {
        int(state.node_id): state
        for state in states
    }

    expected = (
        int(tunnel.iran_node_id),
        int(tunnel.exit_node_id),
    )

    return all(
        _watchdog_state_usable(
            by_node.get(node_id),
            now,
        )
        for node_id in expected
    )



# TWINPANEL_TUNNEL_DIVERSITY_FAILOVER_V50
#
# Multiple tunnel transports may stay ONLINE simultaneously.
# Only one member of each Iran->Exit pair receives service_routes.
#
# Lower priority value = preferred route.
#
# Failover:
#   current route unhealthy -> switch immediately to next usable.
#
# Failback:
#   preferred route must remain healthy for 45 seconds before
#   traffic is moved back to it.
#

_SERVICE_ROUTE_FAILBACK_HOLD_SECONDS = 45

_service_route_selected: dict[
    tuple[int, int],
    int,
] = {}

_service_route_failback_candidate: dict[
    tuple[int, int],
    tuple[int, datetime],
] = {}


def _service_route_member_usable(
    db: Session,
    tunnel: Tunnel,
    now: datetime,
) -> bool:
    return bool(
        tunnel.is_active
        and tunnel.status == TunnelStatus.ONLINE
        and _watchdog_tunnel_fully_usable(
            db,
            tunnel,
            now,
        )
    )


def _select_service_route_tunnel_ids(
    db: Session,
    rows: list[Tunnel],
    now: datetime,
) -> set[int]:

    groups: dict[
        tuple[int, int],
        list[Tunnel],
    ] = {}

    for tunnel in rows:
        key = (
            int(tunnel.iran_node_id),
            int(tunnel.exit_node_id),
        )

        groups.setdefault(
            key,
            [],
        ).append(tunnel)

    selected_ids: set[int] = set()

    # TWINPANEL_TUNNEL_FAILOVER_STATE_V50_FIX
    #
    # rows is node-scoped inside /desired. Do NOT remove election
    # state merely because another Iran/Exit pair is absent from
    # this node's response. Only remove pairs that no longer have
    # any active Tunnel in the database.
    live_keys = {
        (
            int(iran_node_id),
            int(exit_node_id),
        )
        for iran_node_id, exit_node_id in (
            db.query(
                Tunnel.iran_node_id,
                Tunnel.exit_node_id,
            )
            .filter(
                Tunnel.is_active.is_(True)
            )
            .distinct()
            .all()
        )
    }

    for key in list(
        _service_route_selected
    ):
        if key not in live_keys:
            _service_route_selected.pop(
                key,
                None,
            )
            _service_route_failback_candidate.pop(
                key,
                None,
            )

    for key, members in groups.items():

        members = sorted(
            members,
            key=lambda t: (
                int(t.priority or 100),
                int(t.id),
            ),
        )

        usable = [
            tunnel
            for tunnel in members
            if _service_route_member_usable(
                db,
                tunnel,
                now,
            )
        ]

        # TWINPANEL_SERVICE_ROUTE_MANAGER_AUTHORITY_V5
        #
        # Legacy peer-state can briefly become stale between Agent
        # reports. Never withdraw the service route when Transport
        # Manager still has a healthy active physical member.
        if not usable:
            manager_usable = []

            for candidate in members:
                active_name = str(
                    candidate.active_transport
                    or ""
                ).strip().lower()

                if not active_name:
                    continue

                member_row = (
                    db.query(TunnelTransport)
                    .filter(
                        TunnelTransport.tunnel_id
                        == int(candidate.id),
                        TunnelTransport.transport
                        == active_name,
                        TunnelTransport.enabled.is_(True),
                    )
                    .first()
                )

                aggregate_online = (
                    str(
                        getattr(
                            candidate.status,
                            "value",
                            candidate.status,
                        )
                        or ""
                    ).strip().lower()
                    == "online"
                )

                member_online = bool(
                    member_row
                    and str(
                        member_row.status
                        or ""
                    ).strip().lower()
                    == "online"
                )

                if aggregate_online and member_online:
                    manager_usable.append(candidate)

            if manager_usable:
                usable = manager_usable

        current_id = (
            _service_route_selected.get(
                key
            )
        )

        current = next(
            (
                tunnel
                for tunnel in usable
                if (
                    current_id is not None
                    and int(tunnel.id)
                    == int(current_id)
                )
            ),
            None,
        )

        # No usable member -> fail closed.
        if not usable:
            if current_id is not None:
                print(
                    "[TunnelFailover] "
                    f"pair={key[0]}->{key[1]} "
                    f"route={current_id} -> none",
                    flush=True,
                )

            _service_route_selected.pop(
                key,
                None,
            )

            _service_route_failback_candidate.pop(
                key,
                None,
            )

            continue

        best = usable[0]

        # Current route died/staled:
        # switch immediately.
        if current is None:

            old_id = current_id

            _service_route_selected[
                key
            ] = int(best.id)

            _service_route_failback_candidate.pop(
                key,
                None,
            )

            if old_id != int(best.id):
                print(
                    "[TunnelFailover] "
                    f"pair={key[0]}->{key[1]} "
                    f"route={old_id} -> {best.id} "
                    f"reason=failover",
                    flush=True,
                )

            selected_ids.add(
                int(best.id)
            )

            continue

        # Current already is best.
        if int(current.id) == int(best.id):

            _service_route_failback_candidate.pop(
                key,
                None,
            )

            selected_ids.add(
                int(current.id)
            )

            continue

        current_rank = (
            int(current.priority or 100),
            int(current.id),
        )

        best_rank = (
            int(best.priority or 100),
            int(best.id),
        )

        # A better Primary recovered.
        if best_rank < current_rank:

            candidate = (
                _service_route_failback_candidate.get(
                    key
                )
            )

            if (
                not candidate
                or int(candidate[0])
                != int(best.id)
            ):
                _service_route_failback_candidate[
                    key
                ] = (
                    int(best.id),
                    now,
                )

                selected_ids.add(
                    int(current.id)
                )

                continue

            stable_seconds = (
                now - candidate[1]
            ).total_seconds()

            if (
                stable_seconds
                < _SERVICE_ROUTE_FAILBACK_HOLD_SECONDS
            ):
                selected_ids.add(
                    int(current.id)
                )

                continue

            _service_route_selected[
                key
            ] = int(best.id)

            _service_route_failback_candidate.pop(
                key,
                None,
            )

            print(
                "[TunnelFailover] "
                f"pair={key[0]}->{key[1]} "
                f"route={current.id} -> {best.id} "
                f"reason=failback",
                flush=True,
            )

            selected_ids.add(
                int(best.id)
            )

            continue

        # Current remains preferred.
        _service_route_failback_candidate.pop(
            key,
            None,
        )

        selected_ids.add(
            int(current.id)
        )

    return selected_ids


async def _watchdog_repair_tunnel(
    tunnel_id: int,
    reason: str,
) -> None:
    async with _tunnel_watchdog_repair_lock:
        db = SessionLocal()

        try:
            db.expire_all()

            tunnel = db.get(
                Tunnel,
                tunnel_id,
            )

            if not tunnel or not tunnel.is_active:
                return

            # TWINPANEL_SSH_TUNNEL_WATCHDOG_V47
            # SSH TP27 self-heals through systemd. Never rotate
            # WireGuard ports or rebuild mwg for this transport.
            if _is_ssh_tun(tunnel):
                _tunnel_watchdog_failures[tunnel_id] = 0

                print(
                    f"[TunnelWatchdog] ssh_tun repair skipped "
                    f"tunnel={tunnel_id}",
                    flush=True,
                )
                return

            # A fresh report may have arrived while this tunnel
            # was waiting for the repair lock.
            if _watchdog_tunnel_fully_usable(
                db,
                tunnel,
                datetime.utcnow(),
            ):
                tunnel.status = TunnelStatus.ONLINE
                db.commit()

                _tunnel_watchdog_failures[tunnel_id] = 0
                return

            iran = db.get(
                Node,
                tunnel.iran_node_id,
            )

            exit_node = db.get(
                Node,
                tunnel.exit_node_id,
            )

            if not iran or not exit_node:
                tunnel.status = TunnelStatus.OFFLINE
                db.commit()

                print(
                    f"[TunnelWatchdog] repair aborted "
                    f"tunnel={tunnel_id} missing_node",
                    flush=True,
                )
                return

            # Never use the panel/mother server as the Iran side
            # of an automatically repaired real tunnel.
            if (
                getattr(iran, "is_mother", False)
                or getattr(iran, "agent_url", None) == "local://core"
                or str(iran.public_ip or "").strip()
                in {"127.0.0.1", "localhost"}
            ):
                tunnel.status = TunnelStatus.OFFLINE
                db.commit()

                print(
                    f"[TunnelWatchdog] repair aborted "
                    f"tunnel={tunnel_id} invalid_iran_node",
                    flush=True,
                )
                return

            states = (
                db.query(TunnelPeerState)
                .filter(
                    TunnelPeerState.tunnel_id == tunnel.id
                )
                .all()
            )

            # Require new Agent reports after repair.
            for state in states:
                state.endpoint_reachable = False
                state.tunnel_reachable = False
                state.latency_ms = None
                state.last_error = "watchdog_repair_pending"

            tunnel.status = TunnelStatus.OFFLINE
            tunnel.latency_ms = None

            db.commit()

            _tunnel_watchdog_last_repair[
                tunnel_id
            ] = datetime.utcnow()

            print(
                f"[TunnelWatchdog] repair start "
                f"tunnel={tunnel_id} reason={reason}",
                flush=True,
            )

            wg_port = _tunnel_wg_port(tunnel)

            repair_errors: list[str] = []

            for node in (iran, exit_node):
                try:
                    await _prepare_tunnel_node(
                        node,
                        db,
                        wg_port,
                    )
                except Exception as exc:
                    repair_errors.append(
                        f"node={node.id}:"
                        f"{str(exc)[:250]}"
                    )

            if repair_errors:
                db.expire_all()

                tunnel = db.get(
                    Tunnel,
                    tunnel_id,
                )

                if tunnel:
                    tunnel.status = TunnelStatus.OFFLINE
                    tunnel.latency_ms = None
                    db.commit()

                print(
                    f"[TunnelWatchdog] repair failed "
                    f"tunnel={tunnel_id} "
                    + " | ".join(repair_errors),
                    flush=True,
                )
                return

            # Wait up to 60 seconds for fresh Agent reports
            # and a real ONLINE state.
            for _ in range(30):
                await asyncio.sleep(2)

                db.expire_all()

                current = db.get(
                    Tunnel,
                    tunnel_id,
                )

                if not current:
                    return

                if (
                    current.status == TunnelStatus.ONLINE
                    and _watchdog_tunnel_fully_usable(
                        db,
                        current,
                        datetime.utcnow(),
                    )
                ):
                    _tunnel_watchdog_failures[
                        tunnel_id
                    ] = 0

                    print(
                        f"[TunnelWatchdog] repair success "
                        f"tunnel={tunnel_id} "
                        f"latency={current.latency_ms}",
                        flush=True,
                    )
                    return

            # -------------------------------------------------
            # TWINPANEL_TUNNEL_WG_PORT_FAILOVER_V1
            #
            # A normal rebuild on the existing port succeeded at
            # the control-plane level, but the tunnel still did not
            # become usable. Rotate the UDP port automatically and
            # rebuild BOTH peers with the same new port.
            # -------------------------------------------------
            db.expire_all()

            current = db.get(
                Tunnel,
                tunnel_id,
            )

            if not current:
                return

            old_port = _tunnel_wg_port(current)
            new_port = _next_tunnel_wg_port(current)

            current.wireguard_port = new_port
            current.status = TunnelStatus.OFFLINE
            current.latency_ms = None

            current_states = (
                db.query(TunnelPeerState)
                .filter(
                    TunnelPeerState.tunnel_id
                    == tunnel_id
                )
                .all()
            )

            for state in current_states:
                state.endpoint_reachable = False
                state.tunnel_reachable = False
                state.latency_ms = None
                state.last_error = (
                    "watchdog_port_rotation_pending"
                )
                state.updated_at = datetime.utcnow()

            # Persist BEFORE preparing nodes. This makes the selected
            # port survive API restarts and subsequent watchdog runs.
            db.commit()

            print(
                f"[TunnelWatchdog] port rotation "
                f"tunnel={tunnel_id} "
                f"old_port={old_port} "
                f"new_port={new_port}",
                flush=True,
            )

            rotation_errors: list[str] = []

            for node in (iran, exit_node):
                try:
                    await _prepare_tunnel_node(
                        node,
                        db,
                        new_port,
                    )
                except Exception as exc:
                    rotation_errors.append(
                        f"node={node.id}:"
                        f"{str(exc)[:250]}"
                    )

            if rotation_errors:
                db.expire_all()

                failed = db.get(
                    Tunnel,
                    tunnel_id,
                )

                if failed:
                    failed.status = TunnelStatus.OFFLINE
                    failed.latency_ms = None
                    db.commit()

                print(
                    f"[TunnelWatchdog] port rotation failed "
                    f"tunnel={tunnel_id} "
                    f"port={new_port} "
                    + " | ".join(rotation_errors),
                    flush=True,
                )
                return

            # Wait for fresh Agent reports after port rotation.
            for _ in range(30):
                await asyncio.sleep(2)

                db.expire_all()

                rotated = db.get(
                    Tunnel,
                    tunnel_id,
                )

                if not rotated:
                    return

                if (
                    rotated.status == TunnelStatus.ONLINE
                    and _watchdog_tunnel_fully_usable(
                        db,
                        rotated,
                        datetime.utcnow(),
                    )
                ):
                    _tunnel_watchdog_failures[
                        tunnel_id
                    ] = 0

                    print(
                        f"[TunnelWatchdog] port rotation success "
                        f"tunnel={tunnel_id} "
                        f"port={new_port} "
                        f"latency={rotated.latency_ms}",
                        flush=True,
                    )
                    return

            db.expire_all()

            rotated = db.get(
                Tunnel,
                tunnel_id,
            )

            if rotated:
                rotated.status = TunnelStatus.OFFLINE
                rotated.latency_ms = None
                db.commit()

            print(
                f"[TunnelWatchdog] port rotation timeout "
                f"tunnel={tunnel_id} "
                f"port={new_port}",
                flush=True,
            )

        finally:
            db.close()


async def _tunnel_watchdog_pass() -> None:
    db = SessionLocal()

    repair_candidates: list[
        tuple[int, str]
    ] = []

    try:
        now = datetime.utcnow()

        tunnels = (
            db.query(Tunnel)
            .filter(
                Tunnel.is_active.is_(True)
            )
            .order_by(
                Tunnel.priority.asc(),
                Tunnel.id.asc(),
            )
            .all()
        )

        for tunnel in tunnels:

            # TWINPANEL_MTUNNEL_WATCHDOG_AUTHORITY_V1
            #
            # MTunnel is health-checked by the controller.
            # Legacy Agent peer reports must not override its
            # authoritative TunnelTransport state every 15 seconds.
            if _effective_transport(tunnel) == "mtunnel":
                mt_row = (
                    db.query(TunnelTransport)
                    .filter(
                        TunnelTransport.tunnel_id == tunnel.id,
                        TunnelTransport.transport == "mtunnel",
                    )
                    .first()
                )

                if mt_row:
                    mt_status = str(
                        mt_row.status or ""
                    ).strip().lower()

                    # TWINPANEL_MTUNNEL_WATCHDOG_NODE_GATE_V1
                    iran_node = db.get(
                        Node,
                        tunnel.iran_node_id,
                    )

                    exit_node = db.get(
                        Node,
                        tunnel.exit_node_id,
                    )

                    iran_status = str(
                        getattr(
                            getattr(
                                iran_node,
                                "status",
                                None,
                            ),
                            "value",
                            getattr(
                                iran_node,
                                "status",
                                "",
                            ),
                        )
                        or ""
                    ).strip().lower()

                    exit_status = str(
                        getattr(
                            getattr(
                                exit_node,
                                "status",
                                None,
                            ),
                            "value",
                            getattr(
                                exit_node,
                                "status",
                                "",
                            ),
                        )
                        or ""
                    ).strip().lower()

                    nodes_online = bool(
                        iran_node
                        and exit_node
                        and getattr(
                            iran_node,
                            "retired_at",
                            None,
                        )
                        is None
                        and getattr(
                            exit_node,
                            "retired_at",
                            None,
                        )
                        is None
                        and iran_status == "online"
                        and exit_status == "online"
                    )

                    if (
                        mt_status == "online"
                        and nodes_online
                    ):
                        tunnel.status = TunnelStatus.ONLINE
                        tunnel.is_active = True
                        tunnel.active_transport = "mtunnel"
                        tunnel.preferred_transport = "mtunnel"
                        tunnel.latency_ms = mt_row.latency_ms

                        _tunnel_watchdog_failures[
                            int(tunnel.id)
                        ] = 0

                    else:
                        tunnel.status = TunnelStatus.OFFLINE
                        tunnel.latency_ms = None

                # MTunnel state is authoritative.
                # Do not run old peer-state watchdog logic.
                continue
            states = (
                db.query(TunnelPeerState)
                .filter(
                    TunnelPeerState.tunnel_id
                    == tunnel.id
                )
                .all()
            )

            by_node = {
                int(state.node_id): state
                for state in states
            }

            expected_nodes = (
                int(tunnel.iran_node_id),
                int(tunnel.exit_node_id),
            )

            usable_count = 0
            reasons: list[str] = []

            for node_id in expected_nodes:
                state = by_node.get(
                    node_id
                )

                if not state:
                    reasons.append(
                        f"node={node_id}:missing_report"
                    )
                    continue

                age = _watchdog_state_age_seconds(
                    state,
                    now,
                )

                if (
                    age is None
                    or age
                    > _TUNNEL_REPORT_STALE_SECONDS
                ):
                    # Preserve updated_at so the original report
                    # age remains visible for diagnostics.
                    state.endpoint_reachable = False
                    state.tunnel_reachable = False
                    state.latency_ms = None
                    state.last_error = "stale_report"

                    reasons.append(
                        f"node={node_id}:stale:"
                        f"{int(age) if age is not None else 'unknown'}s"
                    )
                    continue

                if _watchdog_state_usable(
                    state,
                    now,
                ):
                    usable_count += 1
                else:
                    reasons.append(
                        f"node={node_id}:"
                        f"endpoint={state.endpoint_reachable},"
                        f"tunnel={state.tunnel_reachable},"
                        f"error={state.last_error or 'none'}"
                    )

            if usable_count == 2:
                desired_status = TunnelStatus.ONLINE

            elif usable_count == 1:
                desired_status = TunnelStatus.DEGRADED

            else:
                desired_status = TunnelStatus.OFFLINE

            # TWINPANEL_SINGLE_WRITER_AGGREGATE_V6
            #
            # Watchdog/peer reports are telemetry only.
            # Aggregate Tunnel.status is owned by
            # tunnel_transport_manager.
            #
            # Do NOT write tunnel.status here.

            if desired_status == TunnelStatus.ONLINE:
                _tunnel_watchdog_failures[
                    int(tunnel.id)
                ] = 0
                continue

            tunnel_id = int(
                tunnel.id
            )

            failure_count = (
                _tunnel_watchdog_failures.get(
                    tunnel_id,
                    0,
                )
                + 1
            )

            _tunnel_watchdog_failures[
                tunnel_id
            ] = failure_count

            if (
                failure_count
                < _TUNNEL_FAILURE_THRESHOLD
            ):
                continue

            last_repair = (
                _tunnel_watchdog_last_repair.get(
                    tunnel_id
                )
            )

            if last_repair:
                since_repair = (
                    now - last_repair
                ).total_seconds()

                if (
                    since_repair
                    < _TUNNEL_REPAIR_COOLDOWN_SECONDS
                ):
                    continue

            repair_candidates.append(
                (
                    tunnel_id,
                    ";".join(reasons)[:800],
                )
            )

        db.commit()

    finally:
        db.close()

    for tunnel_id, reason in repair_candidates:
        await _watchdog_repair_tunnel(
            tunnel_id,
            reason,
        )


async def tunnel_watchdog_loop() -> None:
    """
    One active watchdog per API host.

    flock prevents duplicate repair loops if Uvicorn
    is ever started with multiple worker processes.
    """

    lock_handle = open(
        "/tmp/vpnshop-tunnel-watchdog.lock",
        "w",
    )

    owns_lock = False

    try:
        try:
            fcntl.flock(
                lock_handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
            owns_lock = True

        except BlockingIOError:
            print(
                "[TunnelWatchdog] another worker owns watchdog lock",
                flush=True,
            )

            while True:
                await asyncio.sleep(3600)

        print(
            "[TunnelWatchdog] started "
            f"interval={_TUNNEL_WATCHDOG_INTERVAL_SECONDS}s "
            f"stale={_TUNNEL_REPORT_STALE_SECONDS}s "
            f"threshold={_TUNNEL_FAILURE_THRESHOLD}",
            flush=True,
        )

        # Small startup grace window.
        await asyncio.sleep(5)

        while True:
            try:
                await _tunnel_watchdog_pass()

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                print(
                    f"[TunnelWatchdog] pass error: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )

            await asyncio.sleep(
                _TUNNEL_WATCHDOG_INTERVAL_SECONDS
            )

    except asyncio.CancelledError:
        print(
            "[TunnelWatchdog] stopped",
            flush=True,
        )
        raise

    finally:
        if owns_lock:
            try:
                fcntl.flock(
                    lock_handle.fileno(),
                    fcntl.LOCK_UN,
                )
            except Exception:
                pass

        lock_handle.close()


@router.get("", response_model=list[TunnelOut], dependencies=[Depends(require_admin)])
def list_tunnels(db: Session = Depends(get_db)):
    return db.query(Tunnel).order_by(Tunnel.priority.asc(), Tunnel.id.desc()).all()



# TWINPANEL_TUNNEL_AUTO_FABRIC_V1
# TWINPANEL_TUNNEL_NODE_AUTO_BOOTSTRAP_V1
async def _ensure_fabric_for_tunnel_node(
    node: Node,
    db: Session,
) -> dict:
    """
    Complete automatic tunnel-node bootstrap.

    From the panel, with saved SSH access:
      1. connect to Node
      2. install/upgrade TwinPanel Agent
      3. install/repair Tunnel Fabric
      4. verify both results

    No manual SSH command is required.
    """

    conn = await ssh_connect_saved(
        node,
        db,
    )

    try:
        # -------------------------------------------------
        # Agent
        # -------------------------------------------------

        agent = await _install_or_upgrade_agent(
            conn,
            node.id,
            api_base="https://api.movilineapp.com",
        )

        if not isinstance(agent, dict):
            raise RuntimeError(
                "پاسخ نصب Node Agent نامعتبر است"
            )

        agent_ok = (
            agent.get("ok") is True
            or str(agent.get("service") or "").strip().lower()
            == "active"
        )

        if not agent_ok:
            raise RuntimeError(
                "Node Agent آماده نشد: "
                + str(
                    agent.get("error")
                    or agent.get("message")
                    or agent
                )[:1200]
            )

        # -------------------------------------------------
        # Tunnel Fabric
        # -------------------------------------------------

        fabric = await _install_tunnel_fabric_base(
            conn,
            node,
        )

        if not isinstance(fabric, dict):
            raise RuntimeError(
                "پاسخ نصب Tunnel Fabric نامعتبر است"
            )

        if not fabric.get("ok", False):
            raise RuntimeError(
                "Tunnel Fabric آماده نشد: "
                + str(
                    fabric.get("error")
                    or fabric.get("message")
                    or fabric
                )[:1200]
            )

        return {
            "ok": True,
            "node_id": int(node.id),
            "node_name": str(node.name),
            "agent": agent,
            "fabric": fabric,
        }

    finally:
        conn.close()
        await conn.wait_closed()


async def create_tunnel(
    payload: TunnelCreate,
    db: Session = Depends(get_db),
):
    iran = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == payload.iran_node_id,
        )
        .first()
    )

    exit_node = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == payload.exit_node_id,
        )
        .first()
    )

    if not iran or iran.node_type != NodeType.IRAN:
        raise HTTPException(
            status_code=400,
            detail="سرور ایران معتبر نیست",
        )

    if (
        getattr(iran, "is_mother", False)
        or getattr(iran, "agent_url", None)
        == "local://core"
        or str(iran.public_ip or "").strip()
        in {"127.0.0.1", "localhost"}
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "سرور پنل نمی‌تواند نود ایران تونل باشد"
            ),
        )

    if (
        not exit_node
        or exit_node.node_type != NodeType.EXIT
    ):
        raise HTTPException(
            status_code=400,
            detail="سرور خارج معتبر نیست",
        )

    # TWINPANEL_TUNNEL_CREATE_SSH_ONLY_V63
    # --------------------------------------------------------
    # Automatic Tunnel Fabric provisioning.
    #
    # The operator only creates the tunnel from Admin -> Tunnels.
    # TwinPanel prepares both peers automatically.
    # --------------------------------------------------------

    try:
        iran_fabric = await _ensure_fabric_for_tunnel_node(
            iran,
            db,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"آماده‌سازی Tunnel Fabric روی "
                f"سرور ایران «{iran.name}» ناموفق بود: "
                f"{str(exc)[:700]}"
            ),
        )


    try:
        exit_fabric = await _ensure_fabric_for_tunnel_node(
            exit_node,
            db,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"آماده‌سازی Tunnel Fabric روی "
                f"سرور خروجی «{exit_node.name}» ناموفق بود: "
                f"{str(exc)[:700]}"
            ),
        )


    if not iran_fabric.get("ok"):
        raise HTTPException(
            status_code=502,
            detail="Tunnel Fabric سرور ایران آماده نشد",
        )

    if not exit_fabric.get("ok"):
        raise HTTPException(
            status_code=502,
            detail="Tunnel Fabric سرور خروجی آماده نشد",
        )


    requested_transport = str(
        payload.transport or "ssh_tun"
    ).strip().lower()

    # Legacy clients may still send "auto".
    # In V63 Auto always means the canonical SSH primary.
    if requested_transport == "auto":
        requested_transport = "ssh_tun"

    # One Iran/Exit pair is one logical tunnel.
    # New logical tunnels always start with SSH Tunnel.
    # Backup transports are managed inside tunnel_transports
    # by the Relay Manager and are never separate tunnels.
    if requested_transport != "ssh_tun":
        raise HTTPException(
            status_code=400,
            detail=(
                "ساخت تونل جدید فقط با SSH Tunnel "
                "انجام می‌شود؛ مسیر پشتیبان به‌صورت "
                "خودکار ساخته می‌شود"
            ),
        )

    if not payload.is_active:
        raise HTTPException(
            status_code=400,
            detail=(
                "تونل جدید باید هنگام ساخت فعال باشد"
            ),
        )

    # TWINPANEL_LOGICAL_TUNNEL_API_V52
    #
    # One Iran/Exit pair = one logical Tunnel.
    # Extra transports belong inside tunnel_transports.
    existing = (
        db.query(Tunnel)
        .filter(
            Tunnel.iran_node_id
            == payload.iran_node_id,
            Tunnel.exit_node_id
            == payload.exit_node_id,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail=(
                "این مسیر قبلاً ساخته شده است. "
                "نوع انتقال را داخل همان تونل "
                "تغییر دهید."
            ),
        )

    tunnel = Tunnel(
        iran_node_id=payload.iran_node_id,
        exit_node_id=payload.exit_node_id,
        transport=requested_transport,
        priority=payload.priority,
        is_active=True,
        status=TunnelStatus.OFFLINE,
        latency_ms=None,
        wireguard_port=None,
    )

    db.add(tunnel)
    db.flush()

    tunnel_id = int(tunnel.id)

    db.add_all([
        TunnelPeerState(
            tunnel_id=tunnel_id,
            node_id=iran.id,
            selected_transport=requested_transport,
            endpoint_reachable=False,
            tunnel_reachable=False,
            last_error="provisioning",
        ),
        TunnelPeerState(
            tunnel_id=tunnel_id,
            node_id=exit_node.id,
            selected_transport=requested_transport,
            endpoint_reachable=False,
            tunnel_reachable=False,
            last_error="provisioning",
        ),
    ])

    # --------------------------------------------------------
    # SSH TUN
    # --------------------------------------------------------

    if requested_transport == "ssh_tun":

        try:
            # TWINPANEL_MANAGED_PREFLIGHT_BEFORE_SSH_V1
            await _tp_managed_preflight_pair(iran, exit_node, db)
            await provision_ssh_tunnel(
                tunnel,
                iran,
                exit_node,
                db,
            )

        except Exception as exc:
            try:
                await cleanup_ssh_tunnel(
                    tunnel,
                    iran,
                    exit_node,
                    db,
                )
            finally:
                db.rollback()

            raise HTTPException(
                status_code=502,
                detail=(
                    "ساخت SSH Tunnel ناموفق بود: "
                    + str(exc)[:700]
                ),
            )

    # --------------------------------------------------------
    # WIREGUARD WARM-STANDBY
    # --------------------------------------------------------

    else:
        wg_port = _tunnel_wg_port(
            tunnel
        )

        try:
            await _prepare_tunnel_node(
                iran,
                db,
                wg_port,
            )

            await _prepare_tunnel_node(
                exit_node,
                db,
                wg_port,
            )

        except Exception as exc:
            db.rollback()

            raise HTTPException(
                status_code=502,
                detail=(
                    "ساخت WireGuard Tunnel "
                    "ناموفق بود: "
                    + str(exc)[:700]
                ),
            )

    # Agent must see the member in desired state.
    db.commit()

    # TWINPANEL_WG_ASYNC_CREATE_V51
    #
    # WireGuard backup is a warm-standby transport.
    # Do not delete it merely because the first synchronous
    # health window did not become ONLINE. Agents keep
    # reconciling and reporting it in the background.
    if requested_transport == "wireguard":
        db.expire_all()

        current = db.get(
            Tunnel,
            tunnel_id,
        )

        if not current:
            raise HTTPException(
                status_code=500,
                detail=(
                    "رکورد WireGuard پس از ساخت "
                    "در دیتابیس پیدا نشد"
                ),
            )

        current.is_active = True
        db.commit()
        db.refresh(current)

        print(
            f"[TunnelCreate] wireguard async "
            f"tunnel={tunnel_id} "
            f"status={current.status.value}",
            flush=True,
        )

        return current


    try:
        result = await _wait_tunnel_online(
            db,
            tunnel_id,
        )

        return result

    except Exception as exc:
        db.rollback()

        current = db.get(
            Tunnel,
            tunnel_id,
        )

        try:
            if (
                current
                and requested_transport
                == "ssh_tun"
            ):
                await cleanup_ssh_tunnel(
                    current,
                    iran,
                    exit_node,
                    db,
                )

        finally:
            current = db.get(
                Tunnel,
                tunnel_id,
            )

            if current:
                db.delete(current)
                db.commit()

        if isinstance(
            exc,
            HTTPException,
        ):
            raise

        raise HTTPException(
            status_code=504,
            detail=(
                "تونل ساخته شد اما Health "
                "نهایی تایید نشد: "
                + str(exc)[:700]
            ),
        )



# TWINPANEL_LOGICAL_TUNNEL_TRANSPORTS_API_V52

# TWINPANEL_MANUAL_TRANSPORT_API_V2
@router.post(
    "/{tunnel_id}/transport-mode",
    dependencies=[Depends(require_admin)],
)
def set_tunnel_transport_mode(
    tunnel_id: int,
    payload: TunnelTransportModeIn,
    db: Session = Depends(get_db),
):
    tunnel = db.get(
        Tunnel,
        tunnel_id,
    )

    if tunnel is None:
        raise HTTPException(
            status_code=404,
            detail="Tunnel not found",
        )

    mode = str(
        payload.mode or ""
    ).strip().lower()

    requested = str(
        payload.transport or ""
    ).strip().lower()

    allowed = {
        "mtunnel",
        "backhaul",
        "ssh_tun",
    }

    if mode not in {
        "auto",
        "manual",
    }:
        raise HTTPException(
            status_code=400,
            detail="Invalid mode",
        )

    rows = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id
            == tunnel_id,
        )
        .order_by(
            TunnelTransport.priority.asc()
        )
        .all()
    )

    if mode == "manual":

        if requested not in allowed:
            raise HTTPException(
                status_code=400,
                detail="Invalid transport",
            )

        selected = next(
            (
                row
                for row in rows
                if str(
                    row.transport or ""
                ).strip().lower()
                == requested
            ),
            None,
        )

        if selected is None:
            raise HTTPException(
                status_code=404,
                detail="Transport not installed",
            )

        if not bool(selected.enabled):
            raise HTTPException(
                status_code=400,
                detail="Transport disabled",
            )

        tunnel.mode = "manual"
        tunnel.active_transport = requested
        tunnel.preferred_transport = requested

        selected_online = (
            str(
                selected.status or ""
            ).strip().lower()
            == "online"
        )

        if selected_online:
            tunnel.status = TunnelStatus.ONLINE
            tunnel.latency_ms = (
                selected.latency_ms
            )
        else:
            tunnel.status = TunnelStatus.OFFLINE
            tunnel.latency_ms = None

        db.commit()
        db.refresh(tunnel)

        return {
            "ok": True,
            "mode": "manual",
            "status": getattr(
                tunnel.status,
                "value",
                str(tunnel.status),
            ),
            "active_transport":
                tunnel.active_transport,
            "preferred_transport":
                tunnel.preferred_transport,
            "transport_status":
                str(selected.status or ""),
        }

    # AUTO MODE
    tunnel.mode = "auto"
    tunnel.preferred_transport = "mtunnel"

    selected = next(
        (
            row
            for row in rows
            if bool(row.enabled)
            and str(
                row.status or ""
            ).strip().lower()
            == "online"
        ),
        None,
    )

    if selected is not None:
        tunnel.active_transport = (
            str(selected.transport)
        )
        tunnel.status = TunnelStatus.ONLINE
        tunnel.latency_ms = (
            selected.latency_ms
        )
    else:
        tunnel.status = TunnelStatus.OFFLINE
        tunnel.latency_ms = None

    db.commit()
    db.refresh(tunnel)

    return {
        "ok": True,
        "mode": "auto",
        "status": getattr(
            tunnel.status,
            "value",
            str(tunnel.status),
        ),
        "active_transport":
            tunnel.active_transport,
        "preferred_transport":
            tunnel.preferred_transport,
    }


@router.get(
    "/{tunnel_id}/transports",
    dependencies=[Depends(require_admin)],
)
def list_tunnel_transports(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    tunnel = db.get(
        Tunnel,
        tunnel_id,
    )

    if not tunnel:
        raise HTTPException(
            status_code=404,
            detail="تونل پیدا نشد",
        )

    rows = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id
            == tunnel_id
        )
        .order_by(
            TunnelTransport.priority.asc(),
            TunnelTransport.id.asc(),
        )
        .all()
    )

    return {
        "tunnel_id": int(tunnel.id),
        "iran_node_id": int(
            tunnel.iran_node_id
        ),
        "exit_node_id": int(
            tunnel.exit_node_id
        ),
        "mode": tunnel.mode,
        "preferred_transport":
            tunnel.preferred_transport,
        "active_transport":
            tunnel.active_transport,
        "last_switch_at": (
            tunnel.last_switch_at.isoformat()
            if tunnel.last_switch_at
            else None
        ),

        # V53: UI can distinguish registered,
        # usable and currently active transports.
        "auto_ready": (
            len([
                item
                for item in rows
                if (
                    item.enabled
                    and item.status == "online"
                )
            ]) >= 2
        ),

        "transports": [
            {
                "id": int(item.id),
                "transport": item.transport,
                "priority": int(item.priority),
                "enabled": bool(item.enabled),
                "status": item.status,
                "latency_ms": item.latency_ms,
                "last_error": item.last_error,

                "active": (
                    item.transport
                    == tunnel.active_transport
                ),

                "preferred": (
                    item.transport
                    == tunnel.preferred_transport
                ),

                "selectable": (
                    bool(item.enabled)
                    and item.status == "online"
                ),

                "last_healthy_at": (
                    item.last_healthy_at.isoformat()
                    if item.last_healthy_at
                    else None
                ),
            }
            for item in rows
        ],
    }


# TWINPANEL_LOGICAL_CONTROL_V53
@router.patch(
    "/{tunnel_id}",
    response_model=TunnelOut,
    dependencies=[Depends(require_admin)],
)
def update_tunnel(
    tunnel_id: int,
    payload: TunnelUpdate,
    db: Session = Depends(get_db),
):
    tunnel = db.get(Tunnel, tunnel_id)

    if not tunnel:
        raise HTTPException(
            status_code=404,
            detail="تونل پیدا نشد",
        )

    data = payload.model_dump(
        exclude_unset=True
    )

    # transport ستون قدیمی سازگاری است.
    # Transportهای فیزیکی داخل tunnel_transports هستند.
    if "transport" in data:
        requested = str(
            data.pop("transport") or ""
        ).strip().lower()

        current = str(
            tunnel.transport or ""
        ).strip().lower()

        if requested and requested != current:
            raise HTTPException(
                status_code=409,
                detail=(
                    "نوع انتقال را از تنظیمات "
                    "همین تونل تغییر دهید."
                ),
            )

    if "mode" in data:
        mode = str(
            data["mode"] or ""
        ).strip().lower()

        if mode not in {
            "manual",
            "auto",
        }:
            raise HTTPException(
                status_code=400,
                detail=(
                    "حالت تونل باید manual "
                    "یا auto باشد"
                ),
            )

        data["mode"] = mode

    if "preferred_transport" in data:
        preferred = str(
            data["preferred_transport"]
            or ""
        ).strip().lower()

        member = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id
                == tunnel.id,
                TunnelTransport.transport
                == preferred,
            )
            .first()
        )

        if not member:
            raise HTTPException(
                status_code=400,
                detail=(
                    "این Transport برای تونل "
                    "ثبت نشده است"
                ),
            )

        # در Manual فقط Transport واقعاً سالم
        # اجازه انتخاب دارد.
        target_mode = str(
            data.get(
                "mode",
                tunnel.mode or "manual",
            )
        ).lower()

        if (
            target_mode == "manual"
            and (
                not member.enabled
                or member.status != "online"
            )
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Transport انتخاب‌شده هنوز "
                    "آماده استفاده نیست"
                ),
            )

        data["preferred_transport"] = (
            preferred
        )

    for key, value in data.items():
        setattr(
            tunnel,
            key,
            value,
        )

    db.commit()
    db.refresh(tunnel)

    return tunnel



# ============================================================
# TWINPANEL_MTUNNEL_HEALTH_V1
# Panel-driven MTunnel health check.
# ============================================================

async def _mtunnel_health_check(
    tunnel: Tunnel,
    db: Session,
) -> dict:

    from ..mtunnel_transport import (
        mtunnel_runtime_values,
        parse_ping_latency,
    )

    iran = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == tunnel.iran_node_id,
        )
        .first()
    )

    exit_node = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == tunnel.exit_node_id,
        )
        .first()
    )

    if not iran or not exit_node:
        return {
            "ok": False,
            "status": "failed",
            "error": "nodes_missing",
        }

    runtime = mtunnel_runtime_values(
        int(tunnel.id)
    )

    result = {
        "ok": False,
        "status": "failed",
        "transport": "mtunnel",
        "tunnel_id": int(tunnel.id),
        "interface": runtime["interface"],
        "service": runtime["service"],
        "iran_ip": runtime["iran_ip"],
        "exit_ip": runtime["exit_ip"],
        "iran": {},
        "exit": {},
        "ping_iran_exit": False,
        "ping_exit_iran": False,
        "latency_ms": None,
        "error": None,
    }

    iran_conn = None
    exit_conn = None

    try:
        iran_conn = await ssh_connect_saved(
            iran,
            db,
        )

        exit_conn = await ssh_connect_saved(
            exit_node,
            db,
        )

        async def inspect_peer(
            conn,
            role: str,
        ) -> dict:

            service = await conn.run(
                (
                    f"systemctl is-active "
                    f"{runtime['service']}"
                ),
                check=False,
            )

            iface = await conn.run(
                (
                    f"ip link show "
                    f"{runtime['interface']}"
                ),
                check=False,
            )

            addr = await conn.run(
                (
                    f"ip -4 addr show dev "
                    f"{runtime['interface']}"
                ),
                check=False,
            )

            stats = await conn.run(
                (
                    f"ip -s link show "
                    f"{runtime['interface']}"
                ),
                check=False,
            )

            return {
                "role": role,
                "service": str(
                    service.stdout or ""
                ).strip(),
                "service_ok": (
                    str(
                        service.stdout or ""
                    ).strip()
                    == "active"
                ),
                "interface_ok": (
                    iface.exit_status == 0
                ),
                "address_ok": (
                    addr.exit_status == 0
                ),
                "interface_text": str(
                    iface.stdout or ""
                )[-1200:],
                "address_text": str(
                    addr.stdout or ""
                )[-1200:],
                "stats": str(
                    stats.stdout or ""
                )[-1800:],
            }

        result["iran"] = await inspect_peer(
            iran_conn,
            "client",
        )

        result["exit"] = await inspect_peer(
            exit_conn,
            "server",
        )

        ping1 = await iran_conn.run(
            (
                f"ping -I {runtime['interface']} "
                f"-c 3 -W 2 "
                f"{runtime['exit_ip']}"
            ),
            check=False,
        )

        ping2 = await exit_conn.run(
            (
                f"ping -I {runtime['interface']} "
                f"-c 3 -W 2 "
                f"{runtime['iran_ip']}"
            ),
            check=False,
        )

        ping1_text = (
            str(ping1.stdout or "")
            + "\n"
            + str(ping1.stderr or "")
        )

        ping2_text = (
            str(ping2.stdout or "")
            + "\n"
            + str(ping2.stderr or "")
        )

        result["ping_iran_exit"] = (
            "0% packet loss"
            in ping1_text
        )

        result["ping_exit_iran"] = (
            "0% packet loss"
            in ping2_text
        )

        latency = parse_ping_latency(
            ping1_text
        )

        if latency is None:
            latency = parse_ping_latency(
                ping2_text
            )

        result["latency_ms"] = latency

        service_ok = (
            result["iran"]["service_ok"]
            and result["exit"]["service_ok"]
        )

        interface_ok = (
            result["iran"]["interface_ok"]
            and result["exit"]["interface_ok"]
        )

        tunnel_ok = (
            result["ping_iran_exit"]
            and result["ping_exit_iran"]
        )

        result["ok"] = (
            service_ok
            and interface_ok
            and tunnel_ok
        )

        if result["ok"]:
            result["status"] = "online"
            result["error"] = None

        else:
            errors = []

            if not service_ok:
                errors.append(
                    "mtunnel_service_inactive"
                )

            if not interface_ok:
                errors.append(
                    "mtunnel_interface_missing"
                )

            if not result["ping_iran_exit"]:
                errors.append(
                    "iran_to_exit_ping_failed"
                )

            if not result["ping_exit_iran"]:
                errors.append(
                    "exit_to_iran_ping_failed"
                )

            result["status"] = "failed"
            result["error"] = "; ".join(
                errors
            )

        return result

    except Exception as exc:
        result["status"] = "failed"
        result["error"] = (
            type(exc).__name__
            + ": "
            + str(exc)[:1200]
        )

        return result

    finally:
        if iran_conn:
            iran_conn.close()
            await iran_conn.wait_closed()

        if exit_conn:
            exit_conn.close()
            await exit_conn.wait_closed()




@router.get("/{tunnel_id}/health", dependencies=[Depends(require_admin)])
async def tunnel_health(tunnel_id: int, db: Session = Depends(get_db)):
    tunnel = db.get(Tunnel, tunnel_id)
    if not tunnel:
        raise HTTPException(status_code=404, detail="تونل پیدا نشد")

    now = datetime.utcnow()

    # TWINPANEL_MTUNNEL_UNIFIED_PANEL_HEALTH_V2
    effective_transport = _effective_transport(
        tunnel
    )

    mtunnel_live = None

    if effective_transport == "mtunnel":
        mtunnel_live = await _mtunnel_health_check(
            tunnel,
            db,
        )

    states = db.query(TunnelPeerState).filter(
        TunnelPeerState.tunnel_id == tunnel.id
    ).all()

    peers = []

    for role, node_id in (
        ("iran", int(tunnel.iran_node_id)),
        ("exit", int(tunnel.exit_node_id)),
    ):
        node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == node_id).first()
        state = next(
            (x for x in states if int(x.node_id) == node_id),
            None
        )

        age = _watchdog_state_age_seconds(state, now)

        if (
            effective_transport == "mtunnel"
            and mtunnel_live is not None
        ):
            side = (
                mtunnel_live.get("iran", {})
                if role == "iran"
                else mtunnel_live.get("exit", {})
            )

            ping_ok = bool(
                mtunnel_live.get(
                    "ping_iran_exit"
                    if role == "iran"
                    else "ping_exit_iran"
                )
            )

            service_ok = bool(
                side.get("service_ok")
            )

            interface_ok = bool(
                side.get("interface_ok")
            )

            usable = bool(
                service_ok
                and interface_ok
                and ping_ok
            )

            peers.append({
                "role": role,
                "node_id": node_id,
                "node_name": node.name if node else None,
                "endpoint_reachable": usable,
                "tunnel_reachable": usable,
                "selected_transport": "mtunnel",
                "latency_ms": mtunnel_live.get("latency_ms"),
                "last_error": (
                    None
                    if usable
                    else (
                        mtunnel_live.get("error")
                        or "mtunnel_health_failed"
                    )
                ),
                "updated_at": now.isoformat(),
                "age_seconds": 0.0,
                "stale": False,
                "usable": usable,
            })

        else:
            peers.append({
                "role": role,
                "node_id": node_id,
                "node_name": node.name if node else None,
                "endpoint_reachable": bool(state and state.endpoint_reachable),
                "tunnel_reachable": bool(state and state.tunnel_reachable),
                "selected_transport": state.selected_transport if state else None,
                "latency_ms": state.latency_ms if state else None,
                "last_error": state.last_error if state else "missing_report",
                "updated_at": state.updated_at.isoformat() if state else None,
                "age_seconds": round(age, 1) if age is not None else None,
                "stale": age is None or age > _TUNNEL_REPORT_STALE_SECONDS,
                "usable": _watchdog_state_usable(state, now),
            })

    # TWINPANEL_MTUNNEL_LIVE_STATE_SYNC_V1
    #
    # The live MTunnel health check is authoritative while
    # MTunnel is the effective transport. Keep TunnelTransport,
    # Tunnel and peer state synchronized with the same result.
    if (
        effective_transport == "mtunnel"
        and mtunnel_live is not None
    ):
        now_sync = datetime.utcnow()

        mt_row = _tp_transport_row(
            db,
            int(tunnel.id),
            "mtunnel",
            90,
        )

        mt_ok = bool(
            mtunnel_live.get("ok")
        )

        mt_latency = (
            mtunnel_live.get("latency_ms")
        )

        mt_row.enabled = True
        mt_row.updated_at = now_sync

        if mt_ok:
            mt_row.status = "online"
            mt_row.latency_ms = mt_latency
            mt_row.last_error = None
            mt_row.last_healthy_at = now_sync

            # TWINPANEL_SINGLE_WRITER_HEALTH_V5
            #
            # Health endpoint is telemetry only.
            # Transport Manager is the sole owner of aggregate:
            #   tunnel.status
            #   tunnel.active_transport
            #   tunnel.last_switch_at
            #
            # Do not steal or rewrite aggregate authority here.

            for peer_state in states:
                peer_state.selected_transport = "mtunnel"
                peer_state.endpoint_reachable = True
                peer_state.tunnel_reachable = True
                peer_state.latency_ms = mt_latency
                peer_state.last_error = None
                peer_state.updated_at = now_sync

        else:
            mt_error = str(
                mtunnel_live.get("error")
                or "mtunnel_health_failed"
            )[:1800]

            mt_row.status = "failed"
            mt_row.latency_ms = None
            mt_row.last_error = mt_error

            # TWINPANEL_SINGLE_WRITER_HEALTH_FAILURE_V5
            #
            # One live health probe is not allowed to mark
            # the aggregate Tunnel OFFLINE.
            # Member telemetry above is enough; Manager debounces it.
            pass

        db.commit()

    last_repair = _tunnel_watchdog_last_repair.get(int(tunnel.id))

    return {
        "ok": True,
        "tunnel": {
            "id": int(tunnel.id),
            "status": tunnel.status.value,
            "is_active": bool(tunnel.is_active),
            "transport": effective_transport,
            "legacy_transport": tunnel.transport,
            "active_transport": tunnel.active_transport,
            "preferred_transport": tunnel.preferred_transport,
            "priority": tunnel.priority,
            "latency_ms": (
                mtunnel_live.get("latency_ms")
                if mtunnel_live is not None
                else tunnel.latency_ms
            ),
            "interface": _health_interface_name(tunnel),
            "wireguard_port": (
                None
                if _is_ssh_tun(tunnel)
                else _tunnel_wg_port(tunnel)
            ),
        },
        "watchdog": {
            "failure_count": _tunnel_watchdog_failures.get(int(tunnel.id), 0),
            "last_repair_at": last_repair.isoformat() if last_repair else None,
        },
        "peers": peers,
    }


@router.post("/{tunnel_id}/prepare", response_model=TunnelOut, dependencies=[Depends(require_admin)])
async def prepare_tunnel(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    tunnel = db.get(
        Tunnel,
        tunnel_id,
    )

    if not tunnel:
        raise HTTPException(
            status_code=404,
            detail="تونل پیدا نشد",
        )

    iran = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == tunnel.iran_node_id,
        )
        .first()
    )

    exit_node = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == tunnel.exit_node_id,
        )
        .first()
    )

    if (
        not iran
        or iran.node_type != NodeType.IRAN
        or getattr(iran, "is_mother", False)
        or getattr(iran, "agent_url", None) == "local://core"
        or str(iran.public_ip or "").strip()
        in {"127.0.0.1", "localhost"}
    ):
        raise HTTPException(
            status_code=400,
            detail="نود ایران واقعی این تونل معتبر نیست",
        )

    if (
        not exit_node
        or exit_node.node_type != NodeType.EXIT
    ):
        raise HTTPException(
            status_code=400,
            detail="سرور خارج این تونل معتبر نیست",
        )

    if _is_ssh_tun(tunnel):
        tunnel.is_active = True
        tunnel.status = TunnelStatus.OFFLINE
        tunnel.latency_ms = None

        db.commit()

        try:
            # TWINPANEL_MANAGED_PREFLIGHT_BEFORE_SSH_V1
            await _tp_managed_preflight_pair(iran, exit_node, db)
            await provision_ssh_tunnel(
                tunnel,
                iran,
                exit_node,
                db,
            )

        except Exception as exc:
            tunnel.status = TunnelStatus.OFFLINE
            tunnel.latency_ms = None
            db.commit()

            raise HTTPException(
                status_code=502,
                detail=(
                    "بررسی/ترمیم SSH Tunnel ناموفق بود: "
                    + str(exc)[:700]
                ),
            )

        return await _wait_tunnel_online(
            db,
            tunnel.id,
        )

    # Legacy WireGuard tunnels
    wg_port = _tunnel_wg_port(tunnel)

    await _prepare_tunnel_node(
        iran,
        db,
        wg_port,
    )

    await _prepare_tunnel_node(
        exit_node,
        db,
        wg_port,
    )

    tunnel.is_active = True
    tunnel.status = TunnelStatus.OFFLINE

    db.commit()

    return await _wait_tunnel_online(
        db,
        tunnel.id,
    )


@router.post("/{tunnel_id}/toggle", response_model=TunnelOut, dependencies=[Depends(require_admin)])
def toggle_tunnel(tunnel_id: int, db: Session = Depends(get_db)):
    tunnel = db.get(Tunnel, tunnel_id)
    if not tunnel:
        raise HTTPException(status_code=404, detail="تونل پیدا نشد")
    tunnel.is_active = not tunnel.is_active
    if not tunnel.is_active:
        tunnel.status = TunnelStatus.OFFLINE
    db.commit()
    db.refresh(tunnel)
    return tunnel


@router.delete("/{tunnel_id}", dependencies=[Depends(require_admin)])
async def delete_tunnel(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    tunnel = db.get(
        Tunnel,
        tunnel_id,
    )

    if not tunnel:
        raise HTTPException(
            status_code=404,
            detail="تونل پیدا نشد",
        )

    # TWINPANEL_LIFECYCLE_DELETE_V1
    #
    # First remove the tunnel from desired-state so the Agent
    # cannot recreate interfaces/routing while cleanup runs.
    tunnel.is_active = False
    tunnel.status = TunnelStatus.OFFLINE
    tunnel.latency_ms = None

    db.commit()
    db.refresh(tunnel)

    cleanup_job = CleanupJob(
        target_type="tunnel",
        target_id=int(tunnel_id),
        action="remove_runtime",
        status="running",
    )

    db.add(cleanup_job)
    db.commit()

    try:
        cleanup = await cleanup_tunnel_runtime(
            tunnel,
            db,
        )

    except Exception as exc:

        cleanup_job.status = "failed"
        cleanup_job.error = str(exc)[:2000]
        cleanup_job.finished_at = datetime.utcnow()
        db.commit()

        # Runtime may be partially cleaned, but the database
        # identity remains and deletion can safely be retried.
        raise HTTPException(
            status_code=409,
            detail=(
                "پاک‌سازی کامل تونل انجام نشد؛ "
                "تونل از دیتابیس حذف نشد. "
                f"جزئیات: {str(exc)[:1800]}"
            ),
        )

    db.query(TunnelPeerState).filter(
        TunnelPeerState.tunnel_id
        == tunnel_id
    ).delete(
        synchronize_session=False
    )

    db.query(TunnelTransport).filter(
        TunnelTransport.tunnel_id
        == tunnel_id
    ).delete(
        synchronize_session=False
    )

    db.delete(tunnel)

    cleanup_job.status = "completed"
    cleanup_job.finished_at = datetime.utcnow()

    db.commit()

    _tunnel_watchdog_failures.pop(
        int(tunnel_id),
        None,
    )

    _tunnel_watchdog_last_repair.pop(
        int(tunnel_id),
        None,
    )

    return {
        "ok": True,
        "deleted_tunnel_id": int(tunnel_id),
        "runtime_cleanup": cleanup,
    }


@router.get("/node/{node_id}/desired")
def desired_tunnels(
    node_id: int,
    x_node_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_node_secret(x_node_secret)

    node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    rows = (
        db.query(Tunnel)
        .filter(
            Tunnel.is_active.is_(True),
            (Tunnel.iran_node_id == node_id) | (Tunnel.exit_node_id == node_id),
        )
        .order_by(Tunnel.priority.asc(), Tunnel.id.asc())
        .all()
    )

    # TWINPANEL_TUNNEL_ROUTE_ELECTION_V50
    selected_service_tunnel_ids = (
        _select_service_route_tunnel_ids(
            db,
            rows,
            datetime.utcnow(),
        )
    )

    output = []
    for tunnel in rows:
        iran = db.query(Node).filter(Node.retired_at.is_(None), Node.id == tunnel.iran_node_id).first()
        exit_node = db.query(Node).filter(Node.retired_at.is_(None), Node.id == tunnel.exit_node_id).first()
        if not iran or not exit_node:
            continue

        self_state = db.query(TunnelPeerState).filter(
            TunnelPeerState.tunnel_id == tunnel.id,
            TunnelPeerState.node_id == node_id,
        ).first()
        if not self_state:
            self_state = TunnelPeerState(tunnel_id=tunnel.id, node_id=node_id)
            db.add(self_state)
            db.flush()

        peer_node_id = tunnel.exit_node_id if node_id == tunnel.iran_node_id else tunnel.iran_node_id
        peer = exit_node if node_id == tunnel.iran_node_id else iran
        peer_state = db.query(TunnelPeerState).filter(
            TunnelPeerState.tunnel_id == tunnel.id,
            TunnelPeerState.node_id == peer_node_id,
        ).first()

        network, iran_addr, exit_addr = _tunnel_addresses(tunnel.id)
        is_iran = node_id == tunnel.iran_node_id

        health_peer_tunnel_ip, health_service = (
            _ssh_tun_health_meta(
                tunnel,
                node_id,
            )
        )

        health_interface = (
            _health_interface_name(tunnel)
        )

        # TWINPANEL_SSH_RELAY_CONTROL_V61
        active_transport = str(
            tunnel.active_transport
            or tunnel.preferred_transport
            or tunnel.transport
            or "ssh_tun"
        ).strip().lower()

        route_interface = _data_interface_name(tunnel)
        route_network = network
        route_local_address = iran_addr if is_iran else exit_addr
        route_peer_tunnel_ip = (
            exit_addr if is_iran else iran_addr
        ).split("/")[0]
        route_exit_tunnel_ip = str(exit_addr).split("/", 1)[0]
        route_health_interface = health_interface
        route_health_peer_tunnel_ip = health_peer_tunnel_ip
        route_health_service = health_service

        if active_transport == "ssh_relay":
            relay_meta = relay_desired_meta(
                db,
                tunnel,
                node_id,
            )
            if relay_meta:
                route_interface = relay_meta["interface"]
                route_network = relay_meta["network"]
                route_local_address = relay_meta["local_address"]
                route_peer_tunnel_ip = relay_meta["peer_tunnel_ip"]
                route_exit_tunnel_ip = relay_meta["exit_tunnel_ip"]
                route_health_interface = relay_meta["health_interface"]
                route_health_peer_tunnel_ip = relay_meta["health_peer_tunnel_ip"]
                route_health_service = relay_meta["health_service"]
            else:
                # Never advertise a relay route without runtime metadata.
                active_transport = "ssh_tun"

        # TWINPANEL_BACKHAUL_ACTIVE_ROUTE_V2
        elif active_transport == "backhaul":

            backhaul_meta = (
                _backhaul_runtime_values(
                    tunnel.id
                )
            )

            route_interface = (
                backhaul_meta[
                    "interface"
                ]
            )

            route_network = (
                backhaul_meta[
                    "network"
                ]
            )

            route_local_address = (
                backhaul_meta[
                    "iran_addr"
                ]
                if is_iran
                else backhaul_meta[
                    "exit_addr"
                ]
            )

            route_peer_tunnel_ip = (
                backhaul_meta[
                    "exit_ip"
                ]
                if is_iran
                else backhaul_meta[
                    "iran_ip"
                ]
            )

            route_exit_tunnel_ip = (
                backhaul_meta[
                    "exit_ip"
                ]
            )

            route_health_interface = (
                backhaul_meta[
                    "interface"
                ]
            )

            route_health_peer_tunnel_ip = (
                route_peer_tunnel_ip
            )

            route_health_service = (
                backhaul_meta[
                    "service"
                ]
            )

        # TWINPANEL_SSH_TUNNEL_DESIRED_V47
        # V61: both SSH transports are externally provisioned.
        if active_transport in {
            "ssh_tun",
            "ssh_relay",
            "backhaul",
        }:
            candidates = [active_transport]
        else:
            transport_policy = str(
                tunnel.transport or "auto"
            ).strip().lower()

            if transport_policy == "ssh_tun":
                candidates = ["ssh_tun"]
            elif transport_policy not in {
                "auto",
                "wireguard",
            }:
                candidates = [
                    transport_policy,
                    "wireguard",
                ]
            else:
                candidates = ["wireguard"]

        # TWINPANEL_TUNNEL_ACTIVE_SERVICE_ROUTE_V50
        route_selected = (
            int(tunnel.id)
            in selected_service_tunnel_ids
        )

        service_routes = (
            _service_routes_for_exit(
                db,
                exit_node,
                route_exit_tunnel_ip,
            )
            if route_selected
            else []
        )

        l2tp_primary_id = _l2tp_primary_tunnel_id(
            db,
            tunnel.iran_node_id,
        )

        if (
            route_selected
            and l2tp_primary_id
            == int(tunnel.id)
        ):
            service_routes.extend(
                _l2tp_routes_for_exit(
                    db,
                    exit_node,
                    route_exit_tunnel_ip,
                )
            )

        output.append({
            "id": tunnel.id,
            "policy": tunnel.transport,
            "active_transport": active_transport,
            "priority": tunnel.priority,

            # TWINPANEL_TUNNEL_ROUTE_META_V50
            "route_selected": route_selected,
            "route_role": (
                "active"
                if route_selected
                else "standby"
            ),

            # Tunnel #30 keeps its legacy production routing
            # on mwg30 until explicit cutover.
            # New SSH tunnels route services through tunX.
            "interface": route_interface,

            # TWINPANEL_SSH_TUNNEL_HEALTH_V47
            "health_interface": route_health_interface,
            "health_peer_tunnel_ip": route_health_peer_tunnel_ip,
            "health_service": route_health_service,

            # TWINPANEL_WG_ASYMMETRIC_PORTS_V46

            "wireguard_port": _tunnel_wg_port(tunnel),

            "wireguard_listen_port": (

                _tunnel_wg_port(tunnel) + 1

                if is_iran

                else _tunnel_wg_port(tunnel)

            ),

            "peer_wireguard_port": (

                _tunnel_wg_port(tunnel)

                if is_iran

                else _tunnel_wg_port(tunnel) + 1

            ),
            "network": route_network,
            "local_address": route_local_address,
            "peer_tunnel_ip": route_peer_tunnel_ip,
            "peer_node_id": peer.id,
            "peer_public_ip": (
                (peer.public_domain or peer.public_ip)
                if getattr(peer, "is_mother", False)
                else peer.public_ip
            ),
            "peer_wireguard_public_key": peer_state.wireguard_public_key if peer_state else None,
            "transport_candidates": candidates,

            # TWINPANEL_SERVICE_ROUTING_V1
            "node_role": "iran" if is_iran else "exit",
            "exit_node_id": exit_node.id,
            "exit_tunnel_ip": route_exit_tunnel_ip,
            "service_routes": service_routes,
        })

    db.commit()
    return output


@router.post("/{tunnel_id}/node/{node_id}/report")
def report_tunnel_peer(
    tunnel_id: int,
    node_id: int,
    payload: TunnelPeerReportIn,
    x_node_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    _require_node_secret(x_node_secret)

    tunnel = db.get(Tunnel, tunnel_id)
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    if node_id not in {tunnel.iran_node_id, tunnel.exit_node_id}:
        raise HTTPException(status_code=403, detail="Node does not belong to tunnel")

    # TWINPANEL_MTUNNEL_REPORT_AUTHORITY_V1
    #
    # MTunnel is externally provisioned and health-checked by
    # the controller. Legacy Agent reports must never overwrite
    # its authoritative online/offline state.
    effective_transport = _effective_transport(
        tunnel
    )

    if effective_transport == "mtunnel":
        # TWINPANEL_SINGLE_WRITER_REPORT_V5
        #
        # MTunnel is controller-managed. Legacy Agent reports must
        # never modify aggregate Tunnel state and must never use
        # stale Node.status as an online/offline gate.
        #
        # Transport Manager V4 is the sole aggregate authority.
        return {
            "ok": True,
            "ignored": True,
            "reason": "transport_manager_authoritative",
            "status": tunnel.status.value,
            "active_transport": tunnel.active_transport,
            "latency_ms": tunnel.latency_ms,
        }

    state = db.query(TunnelPeerState).filter(
        TunnelPeerState.tunnel_id == tunnel_id,
        TunnelPeerState.node_id == node_id,
    ).first()
    if not state:
        state = TunnelPeerState(tunnel_id=tunnel_id, node_id=node_id)
        db.add(state)

    state.wireguard_public_key = payload.wireguard_public_key or state.wireguard_public_key
    state.selected_transport = payload.selected_transport
    state.endpoint_reachable = payload.endpoint_reachable
    state.tunnel_reachable = payload.tunnel_reachable
    state.latency_ms = payload.latency_ms
    state.last_error = payload.last_error
    state.updated_at = datetime.utcnow()

    peer_node_id = tunnel.exit_node_id if node_id == tunnel.iran_node_id else tunnel.iran_node_id
    peer_state = db.query(TunnelPeerState).filter(
        TunnelPeerState.tunnel_id == tunnel_id,
        TunnelPeerState.node_id == peer_node_id,
    ).first()

    # TWINPANEL_TUNNEL_USABLE_HEALTH_V1
    # A peer is usable only when the tunnel path is reachable
    # and Agent did not report routing/reconcile errors.
    state_usable = bool(
        state.tunnel_reachable
        and not state.last_error
    )

    peer_usable = bool(
        peer_state
        and peer_state.tunnel_reachable
        and not peer_state.last_error
    )

    both_online = bool(
        state_usable
        and peer_usable
    )

    one_online = bool(
        state_usable
        or peer_usable
    )

    # TWINPANEL_SINGLE_WRITER_REPORT_V6
    #
    # Agent reports update only peer/transport telemetry.
    # They MUST NOT overwrite aggregate tunnel.status or
    # aggregate tunnel.latency_ms.
    #
    # Aggregate state is owned by tunnel_transport_manager.

    # TWINPANEL_TRANSPORT_HEALTH_SYNC_V53
    #
    # The legacy peer-state remains the live runtime
    # source for the currently selected transport.
    selected_names = {
        str(x).strip().lower()
        for x in (
            state.selected_transport,
            (
                peer_state.selected_transport
                if peer_state
                else None
            ),
        )
        if x
    }

    if len(selected_names) == 1:

        selected_name = next(
            iter(selected_names)
        )

        member = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id
                == tunnel.id,
                TunnelTransport.transport
                == selected_name,
            )
            .first()
        )

        if member:
            member.status = (
                tunnel.status.value
            )

            member.latency_ms = (
                tunnel.latency_ms
            )

            errors = [
                x
                for x in (
                    state.last_error,
                    (
                        peer_state.last_error
                        if peer_state
                        else None
                    ),
                )
                if x
            ]

            member.last_error = (
                "; ".join(errors)
                if errors
                else None
            )

            member.updated_at = (
                datetime.utcnow()
            )

            if (
                tunnel.status
                == TunnelStatus.ONLINE
            ):
                member.last_healthy_at = (
                    datetime.utcnow()
                )

                # Runtime and logical DB agree.
                tunnel.active_transport = (
                    selected_name
                )

    db.commit()

    return {
        "ok": True,
        "status": tunnel.status.value,
        "latency_ms": tunnel.latency_ms,
    }


# ============================================================
# TWINPANEL_BACKHAUL_TRANSPORT_V1
#
# Backhaul is an OPTIONAL physical transport alongside the
# existing SSH Tunnel. Installing it does NOT change the active
# transport and does NOT modify the existing SSH tunnel.
# ============================================================


# TWINPANEL_BACKHAUL_ROUTE_META_V2
def _backhaul_runtime_values(
    tunnel_id: int,
) -> dict:

    tid=int(tunnel_id)
    slot=10 + (tid % 230)

    return {
        "network":
            f"10.253.{slot}.0/24",

        "interface":
            f"bh{tid}",

        "iran_addr":
            f"10.253.{slot}.1/24",

        "exit_addr":
            f"10.253.{slot}.2/24",

        "iran_ip":
            f"10.253.{slot}.1",

        "exit_ip":
            f"10.253.{slot}.2",

        "health_port":
            20000 + (tid % 20000),

        "service":
            f"twinpanel-backhaul-{tid}.service",

        "config":
            (
                "/etc/twinpanel/backhaul/"
                f"tunnel-{tid}.toml"
            ),
    }



async def _backhaul_default_interface(conn) -> str:
    """
    Detect the real public/default interface without assuming
    eth0 / ens3 / ens160.
    """

    value = await cmd(
        conn,
        r"""ip -4 route get 1.1.1.1 2>/dev/null |
awk '{
  for(i=1;i<=NF;i++){
    if($i=="dev"){
      print $(i+1);
      exit
    }
  }
}'""",
        check=False,
    )

    value = str(value or "").strip()

    if not value:
        raise RuntimeError(
            "اینترفیس اصلی شبکه روی سرور تشخیص داده نشد"
        )

    return value.splitlines()[0].strip()


async def _backhaul_remote_binary_ok(conn) -> bool:
    value = await cmd(
        conn,
        (
            "test -x /usr/local/bin/twinpanel-backhaul "
            "&& echo yes || echo no"
        ),
        check=False,
    )

    return str(value).strip() == "yes"


async def _backhaul_copy_binary(
    conn,
    local_binary: str,
) -> None:
    """
    Copy the licensed Backhaul binary from TwinPanel controller
    to the selected node.

    Controller source:
      /root/vpnshop/backhaul/backhaul_premium
    """

    import os
    import asyncssh

    if not os.path.isfile(local_binary):
        raise RuntimeError(
            "فایل Backhaul روی سرور TwinPanel موجود نیست: "
            + local_binary
        )

    await cmd(
        conn,
        "mkdir -p /usr/local/bin",
        check=True,
    )

    async with conn.start_sftp_client() as sftp:
        await sftp.put(
            local_binary,
            "/usr/local/bin/twinpanel-backhaul.tmp",
        )

    await cmd(
        conn,
        (
            "chmod 0755 /usr/local/bin/twinpanel-backhaul.tmp && "
            "mv -f /usr/local/bin/twinpanel-backhaul.tmp "
            "/usr/local/bin/twinpanel-backhaul"
        ),
        check=True,
    )


async def _install_backhaul_peer(
    conn,
    *,
    tunnel_id: int,
    mode: str,
    local_public_ip: str,
    peer_public_ip: str,
    local_addr: str,
    remote_addr: str,
    interface_name: str,
    health_port: int,
    config_path: str,
    service_name: str,
    local_binary: str,
) -> dict:

    if mode not in {"server", "client"}:
        raise RuntimeError("Backhaul mode نامعتبر است")

    public_interface = await _backhaul_default_interface(conn)

    # Never touch the old SSH tunnel / WireGuard / protocol services.
    # Only install Backhaul's own isolated service and interface.

    if not await _backhaul_remote_binary_ok(conn):
        await _backhaul_copy_binary(
            conn,
            local_binary,
        )

    # Check whether our dedicated address already conflicts.
    local_ip = local_addr.split("/", 1)[0]

    conflict = await cmd(
        conn,
        (
            "ip -4 addr show | "
            f"grep -F ' {local_ip}/' || true"
        ),
        check=False,
    )

    if conflict and interface_name not in conflict:
        raise RuntimeError(
            f"آدرس داخلی Backhaul {local_ip} "
            "روی این سرور قبلاً استفاده شده است"
        )

    # TWINPANEL_BACKHAUL_KNOWN_GOOD_CONFIG_V2
    #
    # Based on the production-tested Backhaul v2.0.0-hotfix8
    # configuration. Iran/server owns the [ports] mapping.
    # Exit/client intentionally has no [ports] section.

    ports_block = ""

    if mode == "server":
        ports_block = """
[ports]
forwarder = "iptables"
mapping = [
    "18080",
]
"""

    config = f"""[transport]
type = "tun"
heartbeat_interval = 10
heartbeat_timeout = 25

[tun]
encapsulation = "ipx"
name = "{interface_name}"
local_addr = "{local_addr}"
remote_addr = "{remote_addr}"
health_port = {int(health_port)}
mtu = 1320

[ipx]
mode = "{mode}"
profile = "icmp"
listen_ip = "{local_public_ip}"
dst_ip = "{peer_public_ip}"
interface = "{public_interface}"

[security]
enable_encryption = false

[tuning]
auto_tuning = true
tuning_profile = "balanced"
workers = 0
channel_size = 10000
so_sndbuf = 0
batch_size = 2048

[logging]
log_level = "debug"
""" + ports_block

    # IMPORTANT:
    # intentionally NOT generated:
    #
    # spoof_src_ip
    # spoof_dst_ip
    # custom_packet
    #
    # They broke the tested deployment and are not part of the
    # known-good TwinPanel baseline.

    import base64

    encoded = base64.b64encode(
        config.encode("utf-8")
    ).decode("ascii")

    unit = f"""[Unit]
Description=TwinPanel Backhaul Tunnel {int(tunnel_id)}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/twinpanel-backhaul -c {config_path}
Restart=always
RestartSec=3
LimitNOFILE=1048576
TasksMax=infinity
LimitMEMLOCK=infinity
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

    unit_encoded = base64.b64encode(
        unit.encode("utf-8")
    ).decode("ascii")

    await cmd(
        conn,
        (
            "mkdir -p /etc/twinpanel/backhaul && "
            f"echo '{encoded}' | base64 -d > {config_path} && "
            f"chmod 0600 {config_path} && "
            f"echo '{unit_encoded}' | base64 -d "
            f"> /etc/systemd/system/{service_name} && "
            "systemctl daemon-reload && "
            f"systemctl enable {service_name} >/dev/null 2>&1"
        ),
        check=True,
    )

    # Delete only our own stale interface before service start.
    await cmd(
        conn,
        (
            f"systemctl stop {service_name} >/dev/null 2>&1 || true; "
            f"ip link delete {interface_name} "
            ">/dev/null 2>&1 || true; "
            f"systemctl start {service_name}"
        ),
        timeout=60,
        check=True,
    )

    await __import__("asyncio").sleep(4)

    service_state = await cmd(
        conn,
        f"systemctl is-active {service_name}",
        check=False,
    )

    addr_state = await cmd(
        conn,
        (
            f"ip -4 addr show dev {interface_name} "
            "2>/dev/null || true"
        ),
        check=False,
    )

    if str(service_state).strip() != "active":
        journal = await cmd(
            conn,
            (
                f"journalctl -u {service_name} "
                "-n 40 --no-pager"
            ),
            check=False,
        )

        raise RuntimeError(
            "سرویس Backhaul فعال نشد: "
            + str(journal or service_state)[-1800:]
        )

    return {
        "ok": True,
        "mode": mode,
        "service": str(service_state).strip(),
        "interface": interface_name,
        "interface_ready": interface_name in str(addr_state),
        "public_interface": public_interface,
        "config": config_path,
    }


@router.post(
    "/{tunnel_id}/backhaul/install",
    dependencies=[Depends(require_admin)],
)
async def install_backhaul_transport(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    # TWINPANEL_BACKHAUL_STATE_V1
    """
    Install Backhaul on BOTH peers.

    This endpoint deliberately does not:
      - alter tunnel.transport
      - alter tunnel.active_transport
      - alter tunnel.preferred_transport
      - stop SSH Tunnel
      - change protocol ports
      - create DNAT rules

    So existing production traffic remains untouched.
    """

    import os

    tunnel = (
        db.query(Tunnel)
        .filter(Tunnel.id == tunnel_id)
        .first()
    )

    if not tunnel:
        raise HTTPException(
            status_code=404,
            detail="تونل پیدا نشد",
        )

    iran = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == tunnel.iran_node_id,
        )
        .first()
    )

    exit_node = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == tunnel.exit_node_id,
        )
        .first()
    )

    if not iran or iran.node_type != NodeType.IRAN:
        raise HTTPException(
            status_code=400,
            detail="نود ایران تونل معتبر نیست",
        )

    if not exit_node or exit_node.node_type != NodeType.EXIT:
        raise HTTPException(
            status_code=400,
            detail="نود خروجی تونل معتبر نیست",
        )

    local_binary = (
        "/root/vpnshop/backhaul/backhaul_premium"
    )

    if not os.path.isfile(local_binary):
        raise HTTPException(
            status_code=409,
            detail=(
                "باینری Backhaul هنوز روی TwinPanel قرار نگرفته است: "
                + local_binary
            ),
        )

    # TWINPANEL_BACKHAUL_AUTO_BOOTSTRAP_V1
    #
    # Fully automatic panel flow:
    #   saved SSH
    #   -> Agent install/upgrade
    #   -> Tunnel Fabric install/repair
    # on BOTH Iran and Exit nodes.
    iran_bootstrap = await _ensure_fabric_for_tunnel_node(
        iran,
        db,
    )

    if not iran_bootstrap.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=(
                "آماده‌سازی خودکار نود ایران ناموفق بود: "
                + str(iran_bootstrap)[:1000]
            ),
        )

    exit_bootstrap = await _ensure_fabric_for_tunnel_node(
        exit_node,
        db,
    )

    if not exit_bootstrap.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=(
                "آماده‌سازی خودکار نود خروجی ناموفق بود: "
                + str(exit_bootstrap)[:1000]
            ),
        )

    # TWINPANEL_MANAGED_PREFLIGHT_BEFORE_BACKHAUL_V1
    await _tp_managed_preflight_pair(
        iran,
        exit_node,
        db,
    )

    runtime = _backhaul_runtime_values(tunnel_id)

    row = _tp_transport_row(
        db,
        tunnel_id,
        "backhaul",
        110,
    )

    row.enabled = True
    row.status = "installing"
    row.latency_ms = None
    row.last_error = None
    row.updated_at = datetime.utcnow()

    db.commit()

    iran_conn = None
    exit_conn = None

    try:
        iran_conn = await ssh_connect_saved(
            iran,
            db,
        )

        exit_conn = await ssh_connect_saved(
            exit_node,
            db,
        )

        # Install both configs first.
        iran_result = await _install_backhaul_peer(
            iran_conn,
            tunnel_id=tunnel_id,
            mode="server",
            local_public_ip=str(iran.public_ip),
            peer_public_ip=str(exit_node.public_ip),
            local_addr=runtime["iran_addr"],
            remote_addr=runtime["exit_addr"],
            interface_name=runtime["interface"],
            health_port=runtime["health_port"],
            config_path=runtime["config"],
            service_name=runtime["service"],
            local_binary=local_binary,
        )

        exit_result = await _install_backhaul_peer(
            exit_conn,
            tunnel_id=tunnel_id,
            mode="client",
            local_public_ip=str(exit_node.public_ip),
            peer_public_ip=str(iran.public_ip),
            local_addr=runtime["exit_addr"],
            remote_addr=runtime["iran_addr"],
            interface_name=runtime["interface"],
            health_port=runtime["health_port"],
            config_path=runtime["config"],
            service_name=runtime["service"],
            local_binary=local_binary,
        )

        # Give the two peers time to establish the TUN.
        await __import__("asyncio").sleep(8)

        ping = await cmd(
            iran_conn,
            (
                f"ping -I {runtime['interface']} "
                "-c 4 -W 2 "
                f"{runtime['exit_ip']}"
            ),
            timeout=20,
            check=False,
        )

        ping_ok = (
            "0% packet loss" in str(ping)
            or "0% بسته" in str(ping)
        )

        if not ping_ok:
            iran_log = await cmd(
                iran_conn,
                (
                    f"journalctl -u {runtime['service']} "
                    "-n 35 --no-pager"
                ),
                check=False,
            )

            exit_log = await cmd(
                exit_conn,
                (
                    f"journalctl -u {runtime['service']} "
                    "-n 35 --no-pager"
                ),
                check=False,
            )

            raise HTTPException(
                status_code=502,
                detail=(
                    "Backhaul نصب شد اما TUN بین دو نود "
                    "هنوز پاسخ نمی‌دهد. "
                    "Iran log: "
                    + str(iran_log)[-700:]
                    + " | Exit log: "
                    + str(exit_log)[-700:]
                ),
            )

        row = _tp_transport_row(
            db,
            tunnel_id,
            "backhaul",
            110,
        )

        row.enabled = True
        row.status = "online"
        row.latency_ms = None
        row.last_error = None
        row.last_healthy_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()

        db.commit()

        return {
            "ok": True,
            "installed": True,
            "transport": "backhaul",
            "tunnel_id": tunnel_id,

            # Existing traffic is intentionally unchanged.
            "activated": False,
            "active_transport": tunnel.active_transport,
            "preferred_transport": tunnel.preferred_transport,

            "interface": runtime["interface"],
            "iran_tun_ip": runtime["iran_ip"],
            "exit_tun_ip": runtime["exit_ip"],
            "mtu": 1320,
            "encapsulation": "ipx",
            "profile": "icmp",

            "iran": iran_result,
            "exit": exit_result,

            "ping_ok": True,
            "message": (
                "Backhaul نصب و ارتباط TUN تأیید شد؛ "
                "مسیر فعلی SSH Tunnel تغییر نکرد."
            ),
        }

    except HTTPException as exc:
        db.rollback()

        row = _tp_transport_row(
            db,
            tunnel_id,
            "backhaul",
            110,
        )

        row.status = "failed"
        row.last_error = str(exc.detail)[:1800]
        row.updated_at = datetime.utcnow()

        db.commit()
        raise

    except Exception as exc:
        db.rollback()

        row = _tp_transport_row(
            db,
            tunnel_id,
            "backhaul",
            110,
        )

        row.status = "failed"
        row.last_error = str(exc)[:1800]
        row.updated_at = datetime.utcnow()

        db.commit()

        raise HTTPException(
            status_code=502,
            detail=(
                "نصب Backhaul ناموفق بود: "
                + str(exc)[:700]
            ),
        )

    finally:
        if iran_conn is not None:
            iran_conn.close()
            await iran_conn.wait_closed()

        if exit_conn is not None:
            exit_conn.close()
            await exit_conn.wait_closed()


@router.get(
    "/{tunnel_id}/backhaul/status",
    dependencies=[Depends(require_admin)],
)
async def backhaul_transport_status(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    tunnel = (
        db.query(Tunnel)
        .filter(Tunnel.id == tunnel_id)
        .first()
    )

    if not tunnel:
        raise HTTPException(
            status_code=404,
            detail="تونل پیدا نشد",
        )

    iran = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == tunnel.iran_node_id,
        )
        .first()
    )

    exit_node = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == tunnel.exit_node_id,
        )
        .first()
    )

    if not iran or not exit_node:
        raise HTTPException(
            status_code=404,
            detail="یکی از نودهای تونل پیدا نشد",
        )

    runtime = _backhaul_runtime_values(tunnel_id)

    async def inspect_peer(node, peer_ip):
        conn = await ssh_connect_saved(node, db)

        try:
            service = await cmd(
                conn,
                (
                    f"systemctl is-active "
                    f"{runtime['service']} 2>/dev/null "
                    "|| true"
                ),
                check=False,
            )

            interface = await cmd(
                conn,
                (
                    f"ip -4 addr show dev "
                    f"{runtime['interface']} "
                    "2>/dev/null || true"
                ),
                check=False,
            )

            ping = ""

            if str(service).strip() == "active":
                ping = await cmd(
                    conn,
                    (
                        f"ping -I {runtime['interface']} "
                        f"-c 2 -W 2 {peer_ip}"
                    ),
                    timeout=10,
                    check=False,
                )

            return {
                "service": str(service).strip()
                or "not-installed",
                "interface_ready":
                    runtime["interface"] in str(interface),
                "peer_reachable":
                    "0% packet loss" in str(ping),
            }

        finally:
            conn.close()
            await conn.wait_closed()

    iran_state = await inspect_peer(
        iran,
        runtime["exit_ip"],
    )

    exit_state = await inspect_peer(
        exit_node,
        runtime["iran_ip"],
    )

    online = (
        iran_state["service"] == "active"
        and exit_state["service"] == "active"
        and iran_state["interface_ready"]
        and exit_state["interface_ready"]
        and iran_state["peer_reachable"]
        and exit_state["peer_reachable"]
    )

    return {
        "ok": True,
        "installed": (
            iran_state["service"] == "active"
            or exit_state["service"] == "active"
        ),
        "online": online,
        "transport": "backhaul",
        "activated": (
            str(tunnel.active_transport or "").lower()
            == "backhaul"
        ),
        "active_transport": tunnel.active_transport,
        "interface": runtime["interface"],
        "iran_tun_ip": runtime["iran_ip"],
        "exit_tun_ip": runtime["exit_ip"],
        "iran": iran_state,
        "exit": exit_state,
    }


# TWINPANEL_BACKHAUL_TRANSPORT_V1_END


# ============================================================
# TWINPANEL_DUAL_TRANSPORT_INSTALL_V1
#
# One Iran -> Exit pair.
# Physical transports are installed independently:
#
#   ssh_tun
#   backhaul
#
# Registering the pair itself installs NOTHING remotely.
# ============================================================


def _tp_transport_row(
    db: Session,
    tunnel_id: int,
    transport: str,
    priority: int,
):
    from ..models import TunnelTransport

    row = (
        db.query(TunnelTransport)
        .filter(
            TunnelTransport.tunnel_id == tunnel_id,
            TunnelTransport.transport == transport,
        )
        .first()
    )

    if row:
        return row

    row = TunnelTransport(
        tunnel_id=tunnel_id,
        transport=transport,
        priority=priority,
        enabled=False,
        status="not_installed",
        latency_ms=None,
        last_error=None,
        config_text=None,
    )

    db.add(row)
    db.flush()

    return row


def _tp_tunnel_nodes(
    db: Session,
    tunnel: Tunnel,
):
    iran = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == tunnel.iran_node_id,
        )
        .first()
    )

    exit_node = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == tunnel.exit_node_id,
        )
        .first()
    )

    if (
        not iran
        or iran.node_type != NodeType.IRAN
        or getattr(iran, "is_mother", False)
        or getattr(iran, "agent_url", None) == "local://core"
        or str(iran.public_ip or "").strip()
        in {"127.0.0.1", "localhost"}
    ):
        raise HTTPException(
            status_code=400,
            detail="نود ایران واقعی معتبر نیست",
        )

    if (
        not exit_node
        or exit_node.node_type != NodeType.EXIT
    ):
        raise HTTPException(
            status_code=400,
            detail="نود خروجی معتبر نیست",
        )

    return iran, exit_node


@router.post(
    "/register",
    response_model=TunnelOut,
    dependencies=[Depends(require_admin)],
)
def register_tunnel_pair(
    payload: TunnelCreate,
    db: Session = Depends(get_db),
):
    """
    Create only the logical Iran -> Exit pair.

    No SSH Tunnel, Backhaul, WireGuard, Agent or Fabric is
    installed by this endpoint.
    """

    iran = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == payload.iran_node_id,
        )
        .first()
    )

    exit_node = (
        db.query(Node)
        .filter(
            Node.retired_at.is_(None),
            Node.id == payload.exit_node_id,
        )
        .first()
    )

    if (
        not iran
        or iran.node_type != NodeType.IRAN
        or getattr(iran, "is_mother", False)
        or getattr(iran, "agent_url", None) == "local://core"
        or str(iran.public_ip or "").strip()
        in {"127.0.0.1", "localhost"}
    ):
        raise HTTPException(
            status_code=400,
            detail="سرور ایران معتبر نیست",
        )

    if (
        not exit_node
        or exit_node.node_type != NodeType.EXIT
    ):
        raise HTTPException(
            status_code=400,
            detail="سرور خروجی معتبر نیست",
        )

    existing = (
        db.query(Tunnel)
        .filter(
            Tunnel.iran_node_id == iran.id,
            Tunnel.exit_node_id == exit_node.id,
        )
        .first()
    )

    if existing:
        # TWINPANEL_AUTO_MULTI_TRANSPORT_REGISTER_V3
        _tp_transport_row(
            db,
            int(existing.id),
            "mtunnel",
            90,
        )

        _tp_transport_row(
            db,
            int(existing.id),
            "backhaul",
            100,
        )

        _tp_transport_row(
            db,
            int(existing.id),
            "ssh_tun",
            200,
        )

        existing.preferred_transport = "mtunnel"

        db.commit()
        db.refresh(existing)

        return existing

    tunnel = Tunnel(
        iran_node_id=iran.id,
        exit_node_id=exit_node.id,

        # Compatibility value only.
        # Physical transports are stored in tunnel_transports.
        transport="ssh_tun",

        priority=payload.priority,
        is_active=False,
        status=TunnelStatus.OFFLINE,
        latency_ms=None,
        wireguard_port=None,

        mode="manual",
        preferred_transport=None,
        active_transport=None,
    )

    db.add(tunnel)
    db.flush()

    tunnel_id = int(tunnel.id)

    db.add_all([
        TunnelPeerState(
            tunnel_id=tunnel_id,
            node_id=iran.id,
            selected_transport="mtunnel",
            endpoint_reachable=False,
            tunnel_reachable=False,
            last_error="not_installed",
        ),
        TunnelPeerState(
            tunnel_id=tunnel_id,
            node_id=exit_node.id,
            selected_transport="mtunnel",
            endpoint_reachable=False,
            tunnel_reachable=False,
            last_error="not_installed",
        ),
    ])

    # TWINPANEL_AUTO_MULTI_TRANSPORT_REGISTER_V3
    _tp_transport_row(
        db,
        tunnel_id,
        "mtunnel",
        90,
    )

    _tp_transport_row(
        db,
        tunnel_id,
        "backhaul",
        100,
    )

    _tp_transport_row(
        db,
        tunnel_id,
        "ssh_tun",
        200,
    )

    tunnel.preferred_transport = "mtunnel"

    db.commit()
    db.refresh(tunnel)

    return tunnel


@router.post(
    "/{tunnel_id}/ssh/install",
    dependencies=[Depends(require_admin)],
)
async def install_ssh_transport(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    """
    Install only SSH Tunnel.

    Backhaul is not touched.
    """

    tunnel = db.get(
        Tunnel,
        tunnel_id,
    )

    if not tunnel:
        raise HTTPException(
            status_code=404,
            detail="تونل پیدا نشد",
        )

    iran, exit_node = _tp_tunnel_nodes(
        db,
        tunnel,
    )

    row = _tp_transport_row(
        db,
        tunnel_id,
        "ssh_tun",
        200,
    )

    if (
        row.status == "online"
        and tunnel.active_transport == "ssh_tun"
        and tunnel.status == TunnelStatus.ONLINE
    ):
        return {
            "ok": True,
            "installed": True,
            "transport": "ssh_tun",
            "tunnel_id": tunnel_id,
            "status": "online",
            "message": "SSH Tunnel از قبل فعال است",
        }

    row.enabled = True
    row.status = "installing"
    row.last_error = None
    row.updated_at = datetime.utcnow()

    # TWINPANEL_NON_DISRUPTIVE_SECONDARY_INSTALL_V3
    #
    # Installing a backup transport must never take a healthy
    # aggregate Tunnel offline or replace the active member.
    tunnel.is_active = True
    tunnel.transport = "ssh_tun"

    current_active = str(
        tunnel.active_transport or ""
    ).strip().lower()

    current_online = bool(
        current_active
        and tunnel.status == TunnelStatus.ONLINE
    )

    if not current_online:
        tunnel.latency_ms = None

    db.commit()

    try:
        # Keep the existing SSH Tunnel implementation exactly as-is.
        # Fabric is installed only because the admin explicitly
        # requested SSH Tunnel installation.
        iran_fabric = await _ensure_fabric_for_tunnel_node(
            iran,
            db,
        )

        exit_fabric = await _ensure_fabric_for_tunnel_node(
            exit_node,
            db,
        )

        if not iran_fabric.get("ok"):
            raise RuntimeError(
                "Tunnel Fabric نود ایران آماده نشد"
            )

        if not exit_fabric.get("ok"):
            raise RuntimeError(
                "Tunnel Fabric نود خروجی آماده نشد"
            )

        # TWINPANEL_MANAGED_PREFLIGHT_BEFORE_SSH_V1
        await _tp_managed_preflight_pair(iran, exit_node, db)
        await provision_ssh_tunnel(
            tunnel,
            iran,
            exit_node,
            db,
        )

        result = await _wait_tunnel_online(
            db,
            tunnel_id,
        )

        row = _tp_transport_row(
            db,
            tunnel_id,
            "ssh_tun",
            200,
        )

        row.enabled = True
        row.status = "online"
        row.latency_ms = result.latency_ms
        row.last_error = None
        row.last_healthy_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()

        # TWINPANEL_NON_DISRUPTIVE_SECONDARY_SUCCESS_V3
        #
        # SSH is fallback priority 200. Do not steal authority
        # from an already-online MTunnel/Backhaul.
        current_active = str(
            result.active_transport or ""
        ).strip().lower()

        if (
            not current_active
            or result.status != TunnelStatus.ONLINE
        ):
            result.active_transport = "ssh_tun"
            result.status = TunnelStatus.ONLINE
            result.latency_ms = row.latency_ms

        result.preferred_transport = "mtunnel"
        result.is_active = True

        db.commit()
        db.refresh(result)

        return {
            "ok": True,
            "installed": True,
            "transport": "ssh_tun",
            "tunnel_id": tunnel_id,
            "status": result.status.value,
            "latency_ms": result.latency_ms,
            "message": "SSH Tunnel با موفقیت نصب شد",
        }

    except Exception as exc:
        db.rollback()

        row = _tp_transport_row(
            db,
            tunnel_id,
            "ssh_tun",
            200,
        )

        row.status = "failed"
        row.last_error = str(exc)[:1800]
        row.updated_at = datetime.utcnow()

        db.commit()

        if isinstance(exc, HTTPException):
            raise

        raise HTTPException(
            status_code=502,
            detail=(
                "نصب SSH Tunnel ناموفق بود: "
                + str(exc)[:700]
            ),
        )


# TWINPANEL_DUAL_TRANSPORT_INSTALL_V1_END



# ============================================================
# TWINPANEL_MTUNNEL_HEALTH_ENDPOINT_V1
# Health check callable directly from TwinPanel.
# ============================================================

@router.get(
    "/{tunnel_id}/mtunnel/health",
    dependencies=[Depends(require_admin)],
)
async def mtunnel_health_endpoint(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    tunnel = db.get(
        Tunnel,
        tunnel_id,
    )

    if not tunnel:
        raise HTTPException(
            status_code=404,
            detail="تونل پیدا نشد",
        )

    result = await _mtunnel_health_check(
        tunnel,
        db,
    )

    row = _tp_transport_row(
        db,
        tunnel_id,
        "mtunnel",
        90,
    )

    now = datetime.utcnow()

    if result.get("ok"):

        latency = result.get(
            "latency_ms"
        )

        row.enabled = True
        row.status = "online"
        row.latency_ms = latency
        row.last_error = None
        row.last_healthy_at = now
        row.updated_at = now

        tunnel.is_active = True
        tunnel.active_transport = "mtunnel"
        tunnel.preferred_transport = "mtunnel"
        tunnel.status = TunnelStatus.ONLINE
        tunnel.latency_ms = latency

        peers = (
            db.query(TunnelPeerState)
            .filter(
                TunnelPeerState.tunnel_id
                == tunnel_id
            )
            .all()
        )

        for peer in peers:
            peer.selected_transport = "mtunnel"
            peer.endpoint_reachable = True
            peer.tunnel_reachable = True
            peer.latency_ms = latency
            peer.last_error = None
            peer.updated_at = now

    else:

        error = str(
            result.get("error")
            or "mtunnel_health_failed"
        )[:1800]

        row.enabled = True
        row.status = "failed"
        row.latency_ms = None
        row.last_error = error
        row.updated_at = now

        # TWINPANEL_MANAGER_SINGLE_WRITER_HEALTH_V3
        #
        # A single health request must never flip aggregate Tunnel
        # state. Transport Manager owns debounce/failover decisions.
        # Only the MTunnel member row is marked unhealthy here.
        pass

        peers = (
            db.query(TunnelPeerState)
            .filter(
                TunnelPeerState.tunnel_id
                == tunnel_id
            )
            .all()
        )

        for peer in peers:
            if (
                str(
                    peer.selected_transport
                    or ""
                ).strip().lower()
                == "mtunnel"
            ):
                peer.endpoint_reachable = False
                peer.tunnel_reachable = False
                peer.latency_ms = None
                peer.last_error = error
                peer.updated_at = now

    db.commit()

    result["database_synced"] = True
    result["active_transport"] = (
        tunnel.active_transport
    )
    result["preferred_transport"] = (
        tunnel.preferred_transport
    )
    result["tunnel_status"] = (
        tunnel.status.value
    )

    return result



# ============================================================
# TWINPANEL_MTUNNEL_PANEL_INSTALL_V1
# Fully automatic Iran -> Exit MTunnel installation.
# ============================================================

@router.post(
    "/{tunnel_id}/mtunnel/install",
    dependencies=[Depends(require_admin)],
)
async def install_mtunnel_transport(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    from ..mtunnel_transport import (
        ensure_mtunnel_key,
        install_mtunnel_peer,
        mtunnel_runtime_values,
        parse_ping_latency,
    )

    tunnel = db.get(
        Tunnel,
        tunnel_id,
    )

    if not tunnel:
        raise HTTPException(
            status_code=404,
            detail="تونل پیدا نشد",
        )

    iran, exit_node = _tp_tunnel_nodes(
        db,
        tunnel,
    )

    row = _tp_transport_row(
        db,
        tunnel_id,
        "mtunnel",
        90,
    )

    row.enabled = True
    row.status = "installing"
    row.latency_ms = None
    row.last_error = None
    row.updated_at = datetime.utcnow()

    db.commit()

    iran_conn = None
    exit_conn = None

    try:
        # Auto SSH -> Agent -> Fabric
        iran_bootstrap = (
            await _ensure_fabric_for_tunnel_node(
                iran,
                db,
            )
        )

        exit_bootstrap = (
            await _ensure_fabric_for_tunnel_node(
                exit_node,
                db,
            )
        )

        if not iran_bootstrap.get("ok"):
            raise RuntimeError(
                "آماده‌سازی نود ایران ناموفق بود"
            )

        if not exit_bootstrap.get("ok"):
            raise RuntimeError(
                "آماده‌سازی نود خروجی ناموفق بود"
            )

        await _tp_managed_preflight_pair(
            iran,
            exit_node,
            db,
        )

        runtime = mtunnel_runtime_values(
            tunnel_id
        )

        key = ensure_mtunnel_key(
            tunnel_id
        )

        # Exit is listener/server.
        exit_conn = await ssh_connect_saved(
            exit_node,
            db,
        )

        exit_result = await install_mtunnel_peer(
            exit_conn,
            tunnel_id=tunnel_id,
            role="server",
            address=runtime["exit_addr"],
            peer_ip=str(iran.public_ip),
            key=key,
            runtime=runtime,
        )

        # Iran is client and connects to Exit.
        iran_conn = await ssh_connect_saved(
            iran,
            db,
        )

        iran_result = await install_mtunnel_peer(
            iran_conn,
            tunnel_id=tunnel_id,
            role="client",
            address=runtime["iran_addr"],
            peer_ip=str(exit_node.public_ip),
            key=key,
            runtime=runtime,
        )

        # TWINPANEL_MTUNNEL_AUTO_INSTALL_V2
        #
        # Full controller-driven verification:
        #   - service on both peers
        #   - interface on both peers
        #   - address on both peers
        #   - Iran -> Exit ping
        #   - Exit -> Iran ping
        #
        # Retry automatically before reporting failure.
        await asyncio.sleep(3)

        health = None

        for attempt in range(1, 4):

            health = await _mtunnel_health_check(
                tunnel,
                db,
            )

            if health.get("ok") is True:
                break

            if attempt < 3:
                # Restart ONLY this MTunnel service.
                # Existing SSH / Backhaul / VPN services
                # are intentionally untouched.
                for conn in (
                    exit_conn,
                    iran_conn,
                ):
                    if conn is None:
                        continue

                    await conn.run(
                        (
                            f"systemctl restart "
                            f"{runtime['service']} "
                            ">/dev/null 2>&1 || true"
                        ),
                        check=False,
                    )

                await asyncio.sleep(
                    3 * attempt
                )

        if not health or health.get("ok") is not True:

            iran_side = (
                (health or {})
                .get("iran")
                or {}
            )

            exit_side = (
                (health or {})
                .get("exit")
                or {}
            )

            raise RuntimeError(
                "MTunnel health verification failed after "
                "3 automatic attempts. "
                f"Iran(service={iran_side.get('service_ok')}, "
                f"interface={iran_side.get('interface_ok')}, "
                f"address={iran_side.get('address_ok')}); "
                f"Exit(service={exit_side.get('service_ok')}, "
                f"interface={exit_side.get('interface_ok')}, "
                f"address={exit_side.get('address_ok')}); "
                f"Iran->Exit={health.get('ping_iran_exit')}; "
                f"Exit->Iran={health.get('ping_exit_iran')}; "
                f"error={health.get('error')}"
            )

        latency = health.get(
            "latency_ms"
        )

        row = _tp_transport_row(
            db,
            tunnel_id,
            "mtunnel",
            90,
        )

        row.enabled = True
        row.status = "online"
        row.latency_ms = latency
        row.last_error = None
        row.last_healthy_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()

        tunnel.is_active = True
        tunnel.active_transport = "mtunnel"
        tunnel.preferred_transport = "mtunnel"
        tunnel.status = TunnelStatus.ONLINE
        tunnel.latency_ms = latency

        for peer in (
            db.query(TunnelPeerState)
            .filter(
                TunnelPeerState.tunnel_id
                == tunnel_id
            )
            .all()
        ):
            peer.selected_transport = "mtunnel"
            peer.endpoint_reachable = True
            peer.tunnel_reachable = True
            peer.latency_ms = latency
            peer.last_error = None
            peer.updated_at = datetime.utcnow()

        db.commit()

        # TWINPANEL_MTUNNEL_STABILITY_CHECK_V2
        #
        # Transport Manager runs every few seconds.
        # Wait through at least one manager cycle and verify
        # that MTunnel remains authoritative.
        await asyncio.sleep(4)

        db.expire_all()

        stable_tunnel = db.get(
            Tunnel,
            tunnel_id,
        )

        stable_row = (
            db.query(TunnelTransport)
            .filter(
                TunnelTransport.tunnel_id
                == tunnel_id,
                TunnelTransport.transport
                == "mtunnel",
            )
            .first()
        )

        stable_ok = bool(
            stable_tunnel
            and stable_row
            and stable_tunnel.is_active
            and str(
                stable_tunnel.active_transport
                or ""
            ).strip().lower()
            == "mtunnel"
            and str(
                stable_tunnel.status.value
                if hasattr(
                    stable_tunnel.status,
                    "value",
                )
                else stable_tunnel.status
            ).strip().lower()
            == "online"
            and str(
                stable_row.status
                or ""
            ).strip().lower()
            == "online"
        )

        if not stable_ok:
            raise RuntimeError(
                "MTunnel نصب و Health شد، "
                "اما وضعیت نهایی توسط Transport Core "
                "پایدار نماند"
            )

        return {
            "ok": True,
            "installed": True,
            "transport": "mtunnel",
            "tunnel_id": tunnel_id,
            "status": "online",
            "active_transport": "mtunnel",
            "interface":
                runtime["interface"],
            "iran_tun_ip":
                runtime["iran_ip"],
            "exit_tun_ip":
                runtime["exit_ip"],
            "port":
                runtime["port"],
            "mtu":
                runtime["mtu"],
            "latency_ms":
                latency,
            "encryption":
                "AES-256-GCM",
            "iran":
                iran_result,
            "exit":
                exit_result,
            "message":
                "MTunnel خودکار نصب و "
                "ارتباط دوطرفه تایید شد",
        }

    except Exception as exc:
        db.rollback()

        row = _tp_transport_row(
            db,
            tunnel_id,
            "mtunnel",
            90,
        )

        row.enabled = False
        row.status = "failed"
        row.last_error = str(exc)[:1800]
        row.updated_at = datetime.utcnow()

        db.commit()

        if isinstance(
            exc,
            HTTPException,
        ):
            raise

        raise HTTPException(
            status_code=502,
            detail=(
                "نصب خودکار MTunnel "
                "ناموفق بود: "
                + str(exc)[:1000]
            ),
        )

    finally:
        if iran_conn is not None:
            iran_conn.close()
            await iran_conn.wait_closed()

        if exit_conn is not None:
            exit_conn.close()
            await exit_conn.wait_closed()


# ============================================================
# TWINPANEL_MTUNNEL_REPAIR_AUTO_V2
# Repair uses exactly the same idempotent Auto Install V2.
# ============================================================

@router.post(
    "/{tunnel_id}/mtunnel/repair",
    dependencies=[Depends(require_admin)],
)
async def repair_mtunnel_transport(
    tunnel_id: int,
    db: Session = Depends(get_db),
):
    return await install_mtunnel_transport(
        tunnel_id,
        db,
    )

