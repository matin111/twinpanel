from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

from fastapi import HTTPException

from app import tp27_repair_api_v265 as api


class FakeQuery:
    def __init__(self, row):
        self.row = row

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.row


class FakeDb:
    def __init__(self, tunnel, row):
        self.tunnel = tunnel
        self.row = row
        self.expire_count = 0

    def get(self, model, ident):
        return self.tunnel

    def query(self, model):
        return FakeQuery(self.row)

    def expire_all(self):
        self.expire_count += 1


def fixtures():
    tunnel = SimpleNamespace(
        id=77,
        mode="manual",
        active_transport="tp27_fast",
        preferred_transport="tp27_fast",
    )
    row = SimpleNamespace(
        id=701,
        tunnel_id=77,
        transport="kernel_vxlan",
        enabled=True,
        status="online",
        latency_ms=14.2,
        last_error=None,
        last_healthy_at=datetime(2026, 10, 27, 1, 0, 0),
    )
    return tunnel, row, FakeDb(tunnel, row)


async def main() -> None:
    health_calls: list[tuple[int, str]] = []
    benchmark_calls: list[tuple[int, int]] = []

    async def fake_health_ok(tunnel_id: int, name: str, seed: dict):
        health_calls.append((int(tunnel_id), str(name)))
        return name, {
            "ok": True,
            "latency_ms": 14.2,
            "source": "v351-smoke",
        }

    async def fake_health_bad(tunnel_id: int, name: str, seed: dict):
        health_calls.append((int(tunnel_id), str(name)))
        return name, {
            "ok": False,
            "latency_ms": None,
            "error": "synthetic-health-failure",
        }

    async def fake_benchmark(tunnel_id: int, row_id: int):
        benchmark_calls.append((int(tunnel_id), int(row_id)))
        return {
            "download_mbps": 51.25,
            "upload_mbps": 19.75,
            "weighted_mbps": 41.8,
            "source": "explicit_health_probe_v351",
        }

    async def fake_benchmark_error(tunnel_id: int, row_id: int):
        benchmark_calls.append((int(tunnel_id), int(row_id)))
        raise RuntimeError("synthetic-benchmark-failure")

    original_health = api.smart.candidate_health_remote_v21
    original_benchmark = api.benchmark_transport_explicit_v351

    try:
        # Healthy MANUAL transport: explicit health test must run the bounded
        # benchmark and must not alter production authority.
        tunnel, row, db = fixtures()
        api.smart.candidate_health_remote_v21 = fake_health_ok
        api.benchmark_transport_explicit_v351 = fake_benchmark
        api.smart._candidate_health_cache[(77, "kernel_vxlan")] = {
            "stale": True,
        }

        result = await api._fresh_transport_probe(77, "kernel_vxlan", db)

        assert health_calls == [(77, "kernel_vxlan")]
        assert benchmark_calls == [(77, 701)]
        assert (77, "kernel_vxlan") not in api.smart._candidate_health_cache
        assert result["ok"] is True
        assert result["transport"] == "kernel_vxlan"
        assert result["benchmark_attempted"] is True
        assert result["benchmark"]["download_mbps"] == 51.25
        assert result["benchmark"]["upload_mbps"] == 19.75
        assert result["benchmark_error"] is None
        assert result["production_path_unchanged"] is True
        assert result["mode"] == "manual"
        assert result["active_transport"] == "tp27_fast"
        assert result["preferred_transport"] == "tp27_fast"
        assert tunnel.mode == "manual"
        assert tunnel.active_transport == "tp27_fast"
        assert tunnel.preferred_transport == "tp27_fast"
        assert db.expire_count == 2

        # Failed health must not generate synthetic throughput traffic.
        health_calls.clear()
        benchmark_calls.clear()
        tunnel2, row2, db2 = fixtures()
        api.smart.candidate_health_remote_v21 = fake_health_bad
        api.benchmark_transport_explicit_v351 = fake_benchmark
        result2 = await api._fresh_transport_probe(77, "kernel_vxlan", db2)
        assert result2["ok"] is False
        assert result2["benchmark_attempted"] is False
        assert result2["benchmark"] is None
        assert result2["benchmark_error"] is None
        assert benchmark_calls == []
        assert db2.expire_count == 1
        assert tunnel2.active_transport == "tp27_fast"
        assert tunnel2.preferred_transport == "tp27_fast"

        # Benchmark failure is soft: health/authority remain healthy/unchanged.
        health_calls.clear()
        benchmark_calls.clear()
        tunnel3, row3, db3 = fixtures()
        api.smart.candidate_health_remote_v21 = fake_health_ok
        api.benchmark_transport_explicit_v351 = fake_benchmark_error
        result3 = await api._fresh_transport_probe(77, "kernel_vxlan", db3)
        assert result3["ok"] is True
        assert result3["benchmark_attempted"] is True
        assert result3["benchmark"] is None
        assert "synthetic-benchmark-failure" in result3["benchmark_error"]
        assert benchmark_calls == [(77, 701)]
        assert row3.status == "online"
        assert row3.last_error is None
        assert tunnel3.mode == "manual"
        assert tunnel3.active_transport == "tp27_fast"
        assert tunnel3.preferred_transport == "tp27_fast"

        try:
            await api._fresh_transport_probe(77, "retired-transport", db3)
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("unknown transport was not rejected")

        print("TRANSPORT_CARD_PROBE_V351_SMOKE_OK")

    finally:
        api.smart.candidate_health_remote_v21 = original_health
        api.benchmark_transport_explicit_v351 = original_benchmark


if __name__ == "__main__":
    asyncio.run(main())
