#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

models = (ROOT / "backend/app/models.py").read_text(encoding="utf-8")
router = (ROOT / "backend/app/routers/tunnels.py").read_text(encoding="utf-8")
auto = (ROOT / "backend/app/smart_transport_auto_v21.py").read_text(encoding="utf-8")
ui = (ROOT / "components/smart-transports-runtime-v25.tsx").read_text(encoding="utf-8")

checks = {
    "model_default_manual": 'mode: Mapped[str] = mapped_column(\n        String(16),\n        default="manual"' in models,
    "create_route_manual": 'mode="manual",\n        preferred_transport=None,\n        active_transport=None' in router,
    "auto_manager_respects_manual": 'if _name(tunnel.mode or "manual") != "auto":' in auto,
    "ui_declares_manual_default": 'Production default")}</span><b dir="ltr">manual</b>' in ui,
    "ui_auto_is_explicit_opt_in": 'Enable optional Smart Auto' in ui,
    "ui_auto_confirmation": (
        "window.confirm" in ui
        and "Smart Auto will select only between qualified TP27 Fast and Spoof Tunnel paths." in ui
    ),
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(f"{name}={'OK' if ok else 'FAIL'}")

if failed:
    raise SystemExit("FAILED: " + ", ".join(failed))

print("MANUAL_TRANSPORT_DEFAULT_V191_V202=OK")
