from __future__ import annotations

from app.routers.outbound_performance_v262 import (
    _advanced_diagnostics_script,
    _tuning_audit_script,
    score_benchmark_v262,
)
from app.routers.outbound_performance_v262_runtime import (
    _tuning_apply_script,
    _tuning_rollback_script,
)


def main() -> None:
    advanced = _advanced_diagnostics_script(
        "ext-smoke",
        "standard",
        idle_latency_ms=25.0,
        baseline_download_mbps=120.0,
    )
    compile(advanced, "<outbound-performance-v262-advanced>", "exec")
    for token in (
        '"route": {"final": TAG}',
        "speed.cloudflare.com/__down",
        "speed.cloudflare.com/__up",
        "%{time_appconnect}",
        "%{time_starttransfer}",
        '"parallel_download_mbps"',
        '"parallel_upload_mbps"',
        '"loaded_latency_ms"',
        '"loaded_probe_loss_pct"',
        '"bufferbloat_ms"',
    ):
        assert token in advanced, token

    audit = _tuning_audit_script()
    apply = _tuning_apply_script()
    rollback = _tuning_rollback_script()
    compile(audit, "<outbound-performance-v262-audit>", "exec")
    compile(apply, "<outbound-performance-v262-apply>", "exec")
    compile(rollback, "<outbound-performance-v262-rollback>", "exec")

    assert "net.ipv4.tcp_congestion_control=bbr" in apply
    assert "net.core.default_qdisc=fq" in apply
    assert "/etc/sysctl.d/91-twinpanel-outbound-performance.conf" in apply
    assert "/etc/twinpanel/performance/tcp-accelerator-backup.json" in apply
    assert "restore_runtime" in apply
    assert "except Exception:\n    restore_runtime()\n    raise" in apply
    assert "tcp-accelerator-backup.json" in rollback
    assert 'f"net.ipv4.tcp_congestion_control={old_cc}"' in rollback
    assert 'f"net.core.default_qdisc={old_qdisc}"' in rollback
    for forbidden in (
        "tc qdisc replace",
        "iptables -f",
        "nft flush",
        "ip route flush",
        "ip link set",
        "net.ipv4.tcp_rmem=",
        "net.ipv4.tcp_wmem=",
        "net.core.rmem_max=",
        "net.core.wmem_max=",
        "mtu ",
    ):
        assert forbidden not in apply.lower(), forbidden

    clean = {
        "ok": True,
        "latency_ms": 25.0,
        "jitter_ms": 1.0,
        "probe_loss_pct": 0.0,
        "download_mbps": 200.0,
        "upload_mbps": 80.0,
        "parallel_download_mbps": 280.0,
        "parallel_upload_mbps": 110.0,
        "bufferbloat_ms": 8.0,
    }
    bloated = {**clean, "bufferbloat_ms": 240.0}
    clean_score = score_benchmark_v262(clean, "balanced")
    bloated_score = score_benchmark_v262(bloated, "balanced")
    failed = score_benchmark_v262({"ok": False}, "balanced")
    assert float(clean_score["score"]) > float(bloated_score["score"])
    assert clean_score["score_version"] == 2
    assert failed["score"] == 0.0

    print("outbound performance v262 smoke: ok")


if __name__ == "__main__":
    main()
