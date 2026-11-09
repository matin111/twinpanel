"""Mieru per-user persisted native byte counters: exact identity and baseline safety."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from app.services import modern_quota_runtime_v257 as mod


def main():
    raw = json.dumps({
        "traffic": {"DownloadBytes": 99_999_999, "UploadBytes": 80_000_000},
        "users": {
            "user-a": {"DownloadBytes": 1200, "UploadBytes": 230},
            "user-b": {"DownloadBytes": 999999, "UploadBytes": 777777},
        },
    })
    m = mod._parse_mieru_cumulative_metrics(raw)
    assert m == {"user-a": (230, 1200), "user-b": (777777, 999999)}
    for invalid in (
        json.dumps({"traffic": {"DownloadBytes": 50}}),
        json.dumps({"users": {"user-a": {"DownloadBytes": "120", "UploadBytes": 0}}}),
        json.dumps({"users": {"user-a": {"DownloadBytes": -1, "UploadBytes": 0}}}),
    ):
        try:
            mod._parse_mieru_cumulative_metrics(invalid)
            raise AssertionError("invalid per-user counters accepted")
        except ValueError:
            pass

    # Only matched authenticated credential is charged; never aggregate
    # whole-server traffic or unrelated per-user metric groups.
    devices = [{
        "device_id": 71, "subscription_id": 19,
        "telemetry_identity": "user-a",
    }, {
        "device_id": 72, "subscription_id": 20,
        "telemetry_identity": "user-no-metrics",
    }]
    calls = []
    def fake_apply(db, **kwargs):
        calls.append(kwargs)
        return {"baselined": True, "event": False, "accepted_bytes": 0}
    with patch.object(mod, "_active_sessions", return_value=[]), patch.object(
        mod, "_baseline_or_apply_cumulative", side_effect=fake_apply
    ):
        result = mod._apply_mieru_cumulative_metrics(
            None, node=SimpleNamespace(id=6), devices=devices, metrics=m
        )
    assert result["matched"] == 1 and result["baselined"] == 1
    assert result["accepted_bytes"] == 0
    assert len(calls) == 1
    assert calls[0]["source_key"] == "mieru:user:user-a"
    assert calls[0]["counter_epoch"] == "mieru-persisted-metrics-v1"
    assert calls[0]["uplink"] == 230 and calls[0]["downlink"] == 1200
    print("MIERU_PER_USER_CUMULATIVE_ACCOUNTING_PASS")


if __name__ == "__main__":
    main()
