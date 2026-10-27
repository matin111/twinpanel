from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V46 = ROOT / "backend/app/xray_customer_xhttp_v46.py"
JOBS = ROOT / "backend/app/service_connections_jobs_v28.py"
SELF_HOSTED = ROOT / "backend/app/self_hosted_runtime.py"
MODERN = ROOT / "backend/app/xray_modern_runtime.py"
POLICY = ROOT / "backend/app/xray_customer_profile_policy_v30.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    v46 = V46.read_text(encoding="utf-8")
    jobs = JOBS.read_text(encoding="utf-8")
    self_hosted = SELF_HOSTED.read_text(encoding="utf-8")
    modern = MODERN.read_text(encoding="utf-8")
    policy = POLICY.read_text(encoding="utf-8")

    # Activation order: self-hosted applies V30, then the jobs lifecycle applies
    # V46 before any Xray reconcile job can run.
    require("apply_xray_customer_profile_policy_v30()" in self_hosted, "V30 activation missing")
    require("apply_service_connections_jobs_v28()" in self_hosted, "jobs activation missing")
    require(
        self_hosted.index("apply_xray_customer_profile_policy_v30()")
        < self_hosted.index("apply_service_connections_jobs_v28()"),
        "V46 host hook would run before V30",
    )
    require("from .xray_customer_xhttp_v46 import apply_xray_customer_xhttp_v46" in jobs, "V46 import missing")
    require("apply_xray_customer_xhttp_v46()" in jobs, "V46 activation missing")

    # Exact customer contract requested: WS + XHTTP + TCP TLS only.
    require("PUBLIC_PROFILE_ORDER_V46" in v46, "public profile order missing")
    require("xray_modern_runtime.PROFILE_WS" in v46, "WebSocket missing")
    require("xray_modern_runtime.PROFILE_XHTTP" in v46, "XHTTP missing")
    require("PROFILE_TCP_TLS" in v46, "TCP TLS missing")
    require("xray_modern_runtime.PROFILE_HTTPUPGRADE" in v46, "HTTPUpgrade hidden policy missing")
    require("xray_modern_runtime.PROFILE_GRPC" in v46, "gRPC hidden policy missing")

    # Collision fix: old base+1 target is unsafe; V46 moves only the target.
    require("XHTTP_TARGET_OFFSET_V46 = 1004" in v46, "collision-free XHTTP target missing")
    require("meta[\"offset\"] = int(XHTTP_TARGET_OFFSET_V46)" in v46, "XHTTP offset application missing")
    require("public_base" not in v46.split("def apply_xray_customer_xhttp_v46", 1)[1], "V46 must not change XHTTP public port family")
    require("[\"public_base\"] = 24000" in self_hosted, "stable XHTTP public port family missing")

    # Runtime has a complete REALITY XHTTP profile and stable identity material.
    for token in (
        '("security", "reality")',
        '("type", "xhttp")',
        '("mode", "stream-one")',
        '("pbk", str(state["reality_password"]))',
        '("sid", str(state["short_id_xhttp"]))',
        '"tag": "vless-xhttp-reality"',
        '"mode": "stream-up"',
    ):
        require(token in modern, f"modern XHTTP runtime contract missing: {token}")

    # V30 documents the original collision reason; V46 must preserve the
    # isolated TLS offsets while adding its own private target.
    require("8444..8452" in policy, "original collision rationale missing")
    require("_ensure_modern_xray" in v46, "validated runtime rebuild missing")
    require("provision.listener(conn, target_port, \"tcp\")" in v46, "listener verification missing")

    # Reconcile must extend the existing V41/V36 chain, not replace it.
    require("_original_run_reconcile_job" in v46, "reconcile chain capture missing")
    require("await _original_run_reconcile_job" in v46, "existing reconcile delegation missing")
    require("xray_profile_reconcile_v36._run_reconcile_job = _run_reconcile_job_v46" in v46, "V46 reconcile hook missing")

    # No credential identity generation belongs in this refinement.
    require("uuid.uuid4" not in v46, "V46 must not rotate UUIDs")
    require("x25519" not in v46, "V46 must not generate REALITY identity")

    print("XRAY_CUSTOMER_XHTTP_V46=PASS")


if __name__ == "__main__":
    main()
