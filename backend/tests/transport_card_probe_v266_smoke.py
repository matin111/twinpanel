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


async def main() -> None:
    tunnel = SimpleNamespace(
        id=77,
        mode="manual",
        active_transport="tp27_fast",
        preferred_transport="tp27_fast",
    )
    row = SimpleNamespace(
        enabled=True,
        status="online",
        latency_ms=14.2,
        last_error=None,
        last_healthy_at=datetime(2026, 10, 27, 1, 0, 0),
    )
    db = FakeDb(tunnel, row)

    calls: list[tuple[int, str]] = []

    async def fake_health(tunnel_id: int, name: str, seed: dict):
        calls.append((int(tunnel_id), str(name)))
        return name, {
            "ok": True,
            "latency_ms": 14.2,
            "source": "v266-smoke",
        }

    original = api.smart.candidate_health_remote_v21
    api.smart.candidate_health_remote_v21 = fake_health

    try:
        api.smart._candidate_health_cache[(77, "kernel_vxlan")] = {
            "stale": True,
        }

        result = await api._fresh_transport_probe(
            77,
            "kernel_vxlan",
            db,
        )

        assert calls == [(77, "kernel_vxlan")]
        assert (77, "kernel_vxlan") not in api.smart._candidate_health_cache
        assert result["ok"] is True
        assert result["transport"] == "kernel_vxlan"
        assert result["production_path_unchanged"] is True
        assert result["mode"] == "manual"
        assert result["active_transport"] == "tp27_fast"
        assert result["preferred_transport"] == "tp27_fast"
        assert tunnel.mode == "manual"
        assert tunnel.active_transport == "tp27_fast"
        assert tunnel.preferred_transport == "tp27_fast"
        assert db.expire_count == 1

        try:
            await api._fresh_transport_probe(77, "retired-transport", db)
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("unknown transport was not rejected")

        print("TRANSPORT_CARD_PROBE_V266_SMOKE_OK")

    finally:
        api.smart.candidate_health_remote_v21 = original


if __name__ == "__main__":
    asyncio.run(main())
