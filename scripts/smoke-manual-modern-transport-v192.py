#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
router = (ROOT / "backend/app/routers/modern_transports.py").read_text(encoding="utf-8")
registry = (ROOT / "backend/app/transport_candidates/__init__.py").read_text(encoding="utf-8")
ui_api = (ROOT / "lib/modern-transport-api.ts").read_text(encoding="utf-8")

checks = {
    "api_default_manual": router.count('"production_default": "manual"') >= 2,
    "api_no_smart_auto_default": '"production_default": "smart_auto"' not in router,
    "manual_route_exists": '@router.post("/{tunnel_id}/modern-transports/{transport}/select-manual")' in router,
    "registry_gate": "if name not in ACTIVE_SPECS:" in router,
    "same_tunnel_row_gate": "TunnelTransport.tunnel_id == tunnel_id" in router and "TunnelTransport.transport == name" in router,
    "enabled_gate": "if not bool(row.enabled):" in router,
    "qualified_gate": 'if not bool(view.get("selectable")):' in router,
    "manual_authority": all(token in router for token in (
        'tunnel.mode = "manual"',
        "tunnel.active_transport = name",
        "tunnel.preferred_transport = name",
    )),
    "registry_tp27_fast": '"tp27_fast": TP27_SPEC' in registry,
    "registry_tp27_masque": '"tp27_masque": TP27_MASQUE_SPEC' in registry,
    "registry_tp27_tcp_direct": '"tp27_tcp_direct": TP27_TCP_DIRECT_SPEC' in registry,
    "ui_manual_uses_modern_endpoint": 'mode==="manual"&&transport' in ui_api and '/select-manual`' in ui_api,
    "ui_auto_keeps_legacy_endpoint": '/transport-mode`' in ui_api and 'JSON.stringify({mode})' in ui_api,
    "ui_type_tp27_fast": '|"tp27_fast"' in ui_api,
    "ui_type_tp27_masque": '|"tp27_masque"' in ui_api,
    "ui_type_tp27_tcp_direct": '|"tp27_tcp_direct"' in ui_api,
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(f"{name}={'OK' if ok else 'FAIL'}")

if failed:
    raise SystemExit("FAILED: " + ", ".join(failed))

print("MANUAL_MODERN_TRANSPORT_V192=OK")
