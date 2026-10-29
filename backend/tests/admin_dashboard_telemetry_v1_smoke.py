from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    telemetry_model = ROOT / "backend/app/node_telemetry_models.py"
    runtime_router = ROOT / "backend/app/routers/runtime_endpoints.py"
    main_file = ROOT / "backend/app/main.py"
    dashboard = ROOT / "components/admin-dashboard-runtime.tsx"

    telemetry_source = telemetry_model.read_text(encoding="utf-8")
    runtime_source = runtime_router.read_text(encoding="utf-8")
    main_source = main_file.read_text(encoding="utf-8")
    dashboard_source = dashboard.read_text(encoding="utf-8")

    # Python wiring must at least parse before CI reaches the full API build.
    ast.parse(telemetry_source)
    ast.parse(runtime_source)

    assert '__tablename__ = "node_telemetry"' in telemetry_source
    for field in ("cpu_percent", "memory_percent", "disk_percent", "updated_at"):
        assert field in telemetry_source

    # The compatibility heartbeat must persist all three agent resource values.
    assert '@router.post("/v1/nodes/{node_id}/heartbeat")' in runtime_source
    assert "telemetry.cpu_percent = float(payload.cpu_percent)" in runtime_source
    assert "telemetry.memory_percent = float(payload.memory_percent)" in runtime_source
    assert "telemetry.disk_percent = float(payload.disk_percent)" in runtime_source

    # Admin health must expose the same values that the dashboard consumes.
    assert '"cpu_percent": telemetry.cpu_percent if telemetry else None' in runtime_source
    assert '"memory_percent": telemetry.memory_percent if telemetry else None' in runtime_source
    assert '"disk_percent": telemetry.disk_percent if telemetry else None' in runtime_source

    # Route precedence is intentional: runtime compatibility routes are mounted
    # before the legacy nodes router, so the extended contract wins safely.
    assert main_source.index("app.include_router(runtime_endpoints_router)") < main_source.index(
        "app.include_router(nodes.router)"
    )

    # UI must render the real health values and keep unavailable data explicit.
    assert 'valueOf(health,"cpu_percent","cpu")' in dashboard_source
    assert 'valueOf(health,"memory_percent","ram_percent","memory")' in dashboard_source
    assert 'valueOf(health,"disk_percent","disk")' in dashboard_source
    assert '<MetricBar label="CPU" value={cpu}/>' in dashboard_source
    assert '<MetricBar label="RAM" value={ram}/>' in dashboard_source
    assert '<MetricBar label="Disk" value={disk}/>' in dashboard_source

    # The dashboard's protocol matrix must remain complete.
    for protocol in (
        "cisco",
        "openvpn",
        "wireguard",
        "l2tp",
        "v2ray",
        "hysteria2",
        "tuic",
        "anytls",
        "naive",
        "shadowtls",
        "snell",
        "mieru",
        "trusttunnel",
        "amneziawg",
        "sudoku",
    ):
        assert f'"{protocol}"' in dashboard_source

    print("ADMIN_DASHBOARD_TELEMETRY_V1=PASS")


if __name__ == "__main__":
    main()
