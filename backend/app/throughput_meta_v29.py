from __future__ import annotations

from types import SimpleNamespace

from . import throughput_auto_v27 as v27
from .ssh_tunnel import (
    ssh_tunnel_addresses,
    ssh_tunnel_backhaul_values,
    ssh_tunnel_interface,
)


# ============================================================
# TWINPANEL THROUGHPUT RUNTIME META V29
#
# V27 benchmark metadata originally came from TunnelTransport.config_text.
# Production audit showed legacy/self-hosted Backhaul and generic SSH TUN rows
# can be fully healthy while config_text remains empty. In that state V27
# cannot benchmark them and they remain permanently "unknown" once throughput
# scoring is active.
#
# V29 adds metadata fallback only:
#   * preserve all metadata already supplied by V27
#   * derive Backhaul interface/IPs from TwinPanel's existing deterministic
#     ssh_tunnel_backhaul_values() helper
#   * derive generic SSH TUN interface/IPs from the existing
#     ssh_tunnel_interface()/ssh_tunnel_addresses() helpers
#   * do not provision, restart, route, firewall, mutate DB, or change scoring
# ============================================================


_BASE_BENCHMARK_META = None


def _runtime_tunnel(tunnel_id: int):
    # The helpers used below only require .id. Using a small proxy avoids a DB
    # read and keeps benchmark candidate discovery side-effect free.
    return SimpleNamespace(id=int(tunnel_id))


def benchmark_meta_v29(row, tunnel_id: int) -> dict | None:
    base = _BASE_BENCHMARK_META or v27._benchmark_meta

    existing = base(row, int(tunnel_id))
    if existing is not None:
        return existing

    name = str(getattr(row, "transport", "") or "").strip().lower()
    tunnel = _runtime_tunnel(int(tunnel_id))

    if name == "backhaul":
        runtime = ssh_tunnel_backhaul_values(tunnel)

        interface = str(runtime.get("interface") or "").strip()
        iran_ip = str(runtime.get("iran_ip") or "").strip()
        exit_ip = str(runtime.get("exit_ip") or "").strip()

        if not (interface and iran_ip and exit_ip):
            return None

        return {
            "transport": name,
            "interface": interface,
            "iran_ip": iran_ip,
            "exit_ip": exit_ip,
        }

    if name == "ssh_tun":
        interface = str(ssh_tunnel_interface(tunnel) or "").strip()
        _network, iran_addr, exit_addr = ssh_tunnel_addresses(tunnel)
        iran_ip = str(iran_addr or "").strip().split("/", 1)[0]
        exit_ip = str(exit_addr or "").strip().split("/", 1)[0]

        if not (interface and iran_ip and exit_ip):
            return None

        return {
            "transport": name,
            "interface": interface,
            "iran_ip": iran_ip,
            "exit_ip": exit_ip,
        }

    return None


def install_throughput_meta_v29() -> None:
    global _BASE_BENCHMARK_META

    if _BASE_BENCHMARK_META is None:
        _BASE_BENCHMARK_META = v27._benchmark_meta

    # V27 resolves _benchmark_meta from its module globals at candidate-selection
    # and benchmark time, so replacing only this helper upgrades both paths
    # without duplicating scheduler or scoring logic.
    v27._benchmark_meta = benchmark_meta_v29

    print(
        "TWINPANEL_THROUGHPUT_META_V29_ACTIVE "
        "backhaul_runtime_meta=1 ssh_tun_runtime_meta=1 "
        "scoring_unchanged=1 routes_unchanged=1",
        flush=True,
    )
