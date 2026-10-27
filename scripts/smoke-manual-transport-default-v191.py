#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

models = (ROOT / "backend/app/models.py").read_text(encoding="utf-8")
router = (ROOT / "backend/app/routers/tunnels.py").read_text(encoding="utf-8")
auto = (ROOT / "backend/app/smart_transport_auto_v21.py").read_text(encoding="utf-8")
ui = (ROOT / "components/tunnel-control-center-v1.tsx").read_text(encoding="utf-8")
api = (ROOT / "lib/modern-transport-api.ts").read_text(encoding="utf-8")

checks = {
    "model_default_manual": 'mode: Mapped[str] = mapped_column(\n        String(16),\n        default="manual"' in models,
    "create_route_manual": 'mode="manual",\n        preferred_transport=None,\n        active_transport=None' in router,
    "auto_manager_respects_manual": 'if _name(tunnel.mode or "manual") != "auto":' in auto,
    "ui_declares_manual_mode": 'mode==="auto"?"SMART AUTO":"MANUAL"' in ui,
    "ui_auto_is_explicit_opt_in": 'Enable Smart Auto' in ui,
    "ui_manual_health_based": 'const manualSelectable=Boolean(row.manual_selectable);' in ui,
    "ui_manual_not_bound_to_auto_gate": 'disabled={Boolean(busy)||isActive||!manualSelectable}' in ui,
    "ui_manual_cutover_uses_endpoint": 'modernTransportApi.setMode(selectedId,"manual",name)' in ui,
    "api_manual_readiness_contract": 'manual_selectable?:boolean;' in api,
    "api_fresh_probe_contract": 'manual_selection_requires_fresh_probe?:boolean;' in api,
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(f"{name}={'OK' if ok else 'FAIL'}")

if failed:
    raise SystemExit("FAILED: " + ", ".join(failed))

print("MANUAL_TRANSPORT_DEFAULT_V191_V289=OK")
