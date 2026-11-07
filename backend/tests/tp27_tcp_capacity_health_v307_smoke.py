from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPAIR = ROOT / "backend/app/tp27_self_repair_v265.py"
TP27 = ROOT / "backend/app/transport_candidates/tp27_fast.py"


def _load_capacity_function(name: str = "_tcp_throughput_health", path: Path = REPAIR):
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
    node = next(
        item for item in ast.parse(source).body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    namespace = {
        "Any": Any,
        "datetime": datetime,
        "THROUGHPUT_MAX_SAMPLE_AGE_SECONDS": 900,
        "THROUGHPUT_CRITICAL_Mbps": 3.0,
        "STABILITY_REVISION": 304,
        "tp27_fast": SimpleNamespace(MTU=1400),
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


def main() -> None:
    measure = _load_capacity_function()
    now = 2_000_000_000.0

    def make(down: float, up: float, age: float):
        return {"smart_auto_v21": {"throughput": {
            "download_mbps": down,
            "upload_mbps": up,
            "measured_at_epoch": now - age,
            "source": "explicit_health_probe_v351",
        }}}

    assert measure({}, now_epoch=now)["status"] == "unknown"
    assert measure(make(0.4, 0.3, 60), now_epoch=now)["confirmed_slow"] is True
    assert measure(make(0.4, 0.3, 60), now_epoch=now)["status"] == "slow"

    # A single asymmetric slow direction is not sufficient to force a repair.
    assert measure(make(0.4, 22, 60), now_epoch=now)["confirmed_slow"] is False
    assert measure(make(50, 22, 60), now_epoch=now)["status"] == "measured"

    # Previous SmartAuto throughput samples cannot label the present link fast
    # or slow. This is particularly important when a carrier changed profile.
    stale = measure(make(0.4, 0.3, 3600), now_epoch=now)
    assert stale["status"] == "stale"
    assert stale["confirmed_slow"] is False

    assert measure(make(0.2, 0.2, -90), now_epoch=now)["status"] == "stale"
    assert measure(make(-1, 0.2, 30), now_epoch=now)["status"] == "unknown"

    repair_meta = _load_capacity_function("_repair_meta")
    existing = {
        "selected_profile": "gre-fou",
        "smart_auto_v21": {"throughput": {"download_mbps": 0.3}},
    }
    args = dict(rt={}, health={}, attempts=[], source="manual", fou_port=None)
    switched = repair_meta(existing, profile="gre-native", **args)
    assert switched["smart_auto_v21"]["throughput"] is None
    assert switched["selected_profile"] == "gre-native"

    retained = repair_meta(existing, profile="gre-fou", **args)
    assert retained["smart_auto_v21"]["throughput"]["download_mbps"] == 0.3

    installer = _load_capacity_function("_invalidate_profile_throughput", TP27)
    out = installer({"selected_profile": "gre-native"}, "gre-fou")
    assert out["smart_auto_v21"]["throughput"] is None
    assert installer({"selected_profile": "gre-native"}, "gre-native") == {
        "selected_profile": "gre-native",
    }
    assert installer({"selected_profile": "gre-native"}, None) == {
        "selected_profile": "gre-native",
    }

    repair_source = REPAIR.read_text(encoding="utf-8")
    assert "and not quality[\"confirmed_slow\"]" in repair_source
    assert '"tcp_throughput": _tcp_throughput_health(cfg)' in repair_source
    assert '"healthy": bool(carrier["healthy"])' in repair_source
    assert "THROUGHPUT_MAX_SAMPLE_AGE_SECONDS = 15 * 60" in repair_source
    print("TP27_TCP_CAPACITY_HEALTH_V307=PASS")


if __name__ == "__main__":
    main()
