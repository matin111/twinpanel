from __future__ import annotations

import asyncio
import time

from . import smart_transport_auto_v21 as smart
from .database import SessionLocal
from .models import Node, Tunnel, TunnelTransport
from .routers.provision import ssh_connect_saved
from .transport_benchmark_receiver_wait_v355 import (
    apply_transport_benchmark_receiver_wait_v355,
)
from .transport_candidates.common import close_pair


MARKER = "TWINPANEL_MANUAL_TRANSPORT_BENCHMARK_V351"
_benchmark_lock = asyncio.Lock()

# The explicit admin health action and SmartAuto share the same V21 benchmark
# primitive. Apply V355 before any explicit measurement can observe the old
# fixed 0.5 second receiver-result race.
apply_transport_benchmark_receiver_wait_v355()


async def benchmark_transport_explicit_v351(
    tunnel_id: int,
    row_id: int,
) -> dict:
    """Measure one already-healthy transport without changing tunnel authority.

    Smart Auto intentionally benchmarks only AUTO-mode tunnels. The admin card
    health action is explicit operator intent and may run the same bounded
    internal-L3 benchmark in MANUAL mode after a fresh health probe succeeds.
    This helper writes throughput telemetry only; it never changes mode,
    active/preferred transport, routes, firewall, services, or candidate status.
    """

    async with _benchmark_lock:
        db = SessionLocal()
        ci = ce = None
        try:
            tunnel = db.get(Tunnel, int(tunnel_id))
            row = db.get(TunnelTransport, int(row_id))

            if tunnel is None or not bool(tunnel.is_active):
                raise RuntimeError("explicit_benchmark_tunnel_unavailable")
            if row is None or int(row.tunnel_id) != int(tunnel_id):
                raise RuntimeError("explicit_benchmark_transport_missing")
            if not bool(row.enabled):
                raise RuntimeError("explicit_benchmark_transport_disabled")
            if smart._status(row.status) != "online":
                raise RuntimeError("explicit_benchmark_transport_not_online")

            blocked = smart.auto_block_reason(row)
            if blocked:
                raise RuntimeError(f"explicit_benchmark_policy_blocked:{blocked}")

            meta = smart._benchmark_meta(row, int(tunnel_id))
            if meta is None:
                raise RuntimeError("explicit_benchmark_runtime_metadata_missing")

            iran = db.get(Node, int(tunnel.iran_node_id))
            exit_node = db.get(Node, int(tunnel.exit_node_id))
            if iran is None or exit_node is None:
                raise RuntimeError("explicit_benchmark_nodes_missing")

            ci, ce = await asyncio.gather(
                ssh_connect_saved(iran, db),
                ssh_connect_saved(exit_node, db),
            )

            name = smart._name(row.transport)

            # Exit -> Iran is user download direction. Iran -> Exit is upload.
            down = await smart._one_direction(
                ce,
                ci,
                src=meta["exit_ip"],
                dst=meta["iran_ip"],
                port=smart._port(int(tunnel_id), name, 1),
                label="download",
            )
            up = await smart._one_direction(
                ci,
                ce,
                src=meta["iran_ip"],
                dst=meta["exit_ip"],
                port=smart._port(int(tunnel_id), name, 2),
                label="upload",
            )

            weighted = (0.70 * float(down)) + (0.30 * float(up))
            now_epoch = time.time()

            # Re-read before persistence. A transport disabled or made unhealthy
            # while the bounded measurement was running must not receive a fresh
            # sample. Authority fields are deliberately not written here.
            db.expire_all()
            tunnel = db.get(Tunnel, int(tunnel_id))
            row = db.get(TunnelTransport, int(row_id))
            if tunnel is None or not bool(tunnel.is_active):
                raise RuntimeError("explicit_benchmark_tunnel_changed")
            if row is None or int(row.tunnel_id) != int(tunnel_id):
                raise RuntimeError("explicit_benchmark_transport_changed")
            if not bool(row.enabled) or smart._status(row.status) != "online":
                raise RuntimeError("explicit_benchmark_health_changed")
            blocked = smart.auto_block_reason(row)
            if blocked:
                raise RuntimeError(f"explicit_benchmark_policy_changed:{blocked}")

            sample = {
                "measured_at_epoch": now_epoch,
                "download_mbps": round(float(down), 3),
                "upload_mbps": round(float(up), 3),
                "weighted_mbps": round(float(weighted), 3),
                "download_weight": 0.70,
                "upload_weight": 0.30,
                "streams": int(smart.BENCHMARK_STREAMS),
                "max_bytes_per_direction": int(smart.BENCHMARK_MAX_BYTES),
                "max_seconds_per_direction": float(smart.BENCHMARK_SECONDS),
                "source": "explicit_health_probe_v351",
            }
            smart._set_smart_state(
                row,
                merge={
                    "version": 21,
                    "throughput": sample,
                },
            )
            db.commit()

            print(
                f"{MARKER} "
                f"tunnel={int(tunnel_id)} transport={name} "
                f"down={down:.2f} up={up:.2f} weighted={weighted:.2f}Mbps "
                "authority_unchanged=1",
                flush=True,
            )

            return dict(sample)

        except asyncio.CancelledError:
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            await close_pair(ci, ce)
            db.close()
