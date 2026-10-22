from __future__ import annotations

import json
import os

os.environ.setdefault("APP_SECRET_KEY", "v174-smoke-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///./v174-smoke.db")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET", "v174-smoke-node-secret")

from app.transport_candidates.common import merge_meta_preserving_smart_auto


existing = repr(
    {
        "transport": "tp27_masque",
        "generation": 151,
        "smart_auto_v21": {
            "last_install_attempt_epoch": 1792630988.0,
            "last_install_attempt_at": "2026-10-22T01:03:08Z",
            "last_install_completed_epoch": 1792631031.0,
            "last_install_completed_at": "2026-10-22T01:03:51Z",
            "last_install_outcome": "failed",
            "last_probe_ok": False,
        },
    }
)

incoming = repr(
    {
        "transport": "tp27_masque",
        "generation": 151,
        "selected_port": 29405,
        "attempts": [{"port": 29405, "result": "failed"}],
    }
)

merged = json.loads(merge_meta_preserving_smart_auto(existing, incoming))
state = merged["smart_auto_v21"]

assert merged["selected_port"] == 29405
assert state["last_install_attempt_epoch"] == 1792630988.0
assert state["last_install_attempt_at"] == "2026-10-22T01:03:08Z"
assert state["last_install_completed_epoch"] == 1792631031.0
assert state["last_install_outcome"] == "failed"
assert state["last_probe_ok"] is False

explicit = repr(
    {
        "transport": "tp27_masque",
        "smart_auto_v21": {
            "last_install_outcome": "online",
            "stable_seconds": 60.0,
        },
    }
)

merged_explicit = json.loads(
    merge_meta_preserving_smart_auto(existing, explicit)
)
state_explicit = merged_explicit["smart_auto_v21"]

assert state_explicit["last_install_attempt_epoch"] == 1792630988.0
assert state_explicit["last_install_outcome"] == "online"
assert state_explicit["stable_seconds"] == 60.0

invalid = "not-a-dict"
assert merge_meta_preserving_smart_auto(existing, invalid) == invalid

print("SMARTAUTO_METADATA_V174_SMOKE_OK")
