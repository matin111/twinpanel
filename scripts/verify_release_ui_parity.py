#!/usr/bin/env python3
"""Fail closed when a pinned release would downgrade the admin sales dashboard.

Release publisher checks out *two* different revisions:
  publisher/ = current main (release metadata)
  source/    = the exact, immutable candidate.source_sha
The active server can be newer than candidate.source_sha, so the publisher must
not ship an older chart just because the candidate version number is newer.
"""
from __future__ import annotations

import argparse
from pathlib import Path

PROTECTED_FILES = (
    "components/admin-dashboard-runtime.tsx",
    "components/premium-revenue-chart.tsx",
    "components/premium-revenue-chart.module.css",
    "components/admin-dashboard-server-card.tsx",
    "components/admin-dashboard-server-card.module.css",
    "components/admin-overview-visuals.tsx",
    "components/admin-overview-visuals.module.css",
    "components/admin-dashboard-lower-panels.tsx",
    "components/admin-dashboard-lower-panels.module.css",
    "components/admin-dashboard-network-panels.tsx",
    "components/admin-dashboard-network-panels.module.css",
)


def verify_ui_release(source: Path, reference: Path, *, check_bundle: bool = False) -> None:
    for rel in PROTECTED_FILES:
        source_path = source / rel
        reference_path = reference / rel
        if not source_path.is_file() or not reference_path.is_file():
            raise ValueError(f"Missing required premium dashboard file: {rel}")
        if source_path.read_bytes() != reference_path.read_bytes():
            raise ValueError(
                f"Pinned release source is stale for {rel}; "
                "recreate the release candidate from current main"
            )

    dashboard = (source / PROTECTED_FILES[0]).read_text(encoding="utf-8")
    component = (source / PROTECTED_FILES[1]).read_text(encoding="utf-8")
    css = (source / PROTECTED_FILES[2]).read_text(encoding="utf-8")
    if 'import {PremiumRevenueChart}' not in dashboard or "<PremiumRevenueChart" not in dashboard:
        raise ValueError("PremiumRevenueChart is missing from the actual admin dashboard")
    if not all(marker in component for marker in ("Sales pulse", "seriesVisible", "selectPointer", "subscription_revenue_toman")):
        # Deliberately specific: fail rather than publish a look-alike or a stub.
        raise ValueError("Premium chart interactive feature markers are missing")
    if "@media(prefers-reduced-motion:reduce)" not in css:
        raise ValueError("Premium chart reduced-motion accessibility has been dropped")

    # Do not let a later version silently revert the live server resource
    # monitor to the old four text bars. Preserve both themes and real trends.
    server_card = (source / PROTECTED_FILES[3]).read_text(encoding="utf-8")
    server_css = (source / PROTECTED_FILES[4]).read_text(encoding="utf-8")
    if not all(key in server_card for key in ("ResourceGauge", "NetworkGauge", "serverSample(payload)", "setSamples(before=>")):
        raise ValueError("Live server resource charts are missing from the dashboard")
    if "html[data-theme=\"light\"]" not in server_css or "prefers-reduced-motion:reduce" not in server_css:
        raise ValueError("Server chart light theme or accessibility rules are missing")

    overview = (source / PROTECTED_FILES[5]).read_text(encoding="utf-8")
    overview_css = (source / PROTECTED_FILES[6]).read_text(encoding="utf-8")
    if not all(marker in dashboard for marker in (
        "OverviewKpiCard", "OperationalHealthVisual", "tunnelsLoaded", "nodesLoaded"
    )):
        raise ValueError("Premium admin KPIs or service health status are no longer mounted")
    if not all(marker in overview for marker in (
        "function HealthRow", "export function OperationalHealthVisual",
        "export function OverviewKpiCard", "safeFraction", "aria-valuetext"
    )):
        raise ValueError("Premium admin overview status logic is missing")
    if not all(marker in overview_css for marker in (
        'html[data-theme="light"]', "prefers-reduced-motion:reduce", ".healthTrack", ".kpiValue"
    )):
        raise ValueError("Admin overview light theme or accessibility styles are missing")

    lower = (source / PROTECTED_FILES[7]).read_text(encoding="utf-8")
    lower_css = (source / PROTECTED_FILES[8]).read_text(encoding="utf-8")
    if not all(marker in dashboard for marker in (
        "SubscriptionAnalytics", "RecentPaymentActivity", "ServerFleetVisual",
        "subscriptionsPageV3", "subscriptionBreakdown"
    )):
        raise ValueError("Premium subscription/activity/server dashboards are not mounted")
    if not all(marker in lower for marker in (
        "export function SubscriptionAnalytics", "export function RecentPaymentActivity",
        "export function ServerFleetVisual", "dashboardPaymentAmount",
        "paymentStatus", "aria-valuenow"
    )):
        raise ValueError("Subscription, payment or server visual component is missing")
    if not all(marker in lower_css for marker in (
        'html[data-theme="light"]', "prefers-reduced-motion:reduce", ".donutInner", ".nodeGrid"
    )):
        raise ValueError("Dashboard lower panels light theme, grid or accessibility missing")

    network = (source / PROTECTED_FILES[9]).read_text(encoding="utf-8")
    network_css = (source / PROTECTED_FILES[10]).read_text(encoding="utf-8")
    if not all(marker in dashboard for marker in (
        "TunnelMonitor", "ProtocolMonitor", "tunnelsLoaded", "protocols={protocols}"
    )):
        raise ValueError("New tunnel and protocol monitors are missing from the dashboard")
    if not all(marker in network for marker in (
        "export function TunnelMonitor", "export function ProtocolMonitor",
        "CLASSIC", "setGroup(option.id)", "aria-pressed",
        "reported online nodes", "reported tunnel state"
    )):
        raise ValueError("Tunnel/protocol status, grouping, or honest telemetry logic missing")
    if not all(marker in network_css for marker in (
        'html[data-theme="light"]', "prefers-reduced-motion:reduce",
        ".protocolGrid", ".tunnelRoute", ".protocolState"
    )):
        raise ValueError("Modern tunnel/protocol theme or accessibility styles are missing")
    if not all(marker in lower for marker in ("fleetSummary", "nodeRole")):
        raise ValueError("Modern node fleet status summary or role badges missing")

    if check_bundle:
        bundle = source / ".next/standalone/.next/static"
        if not bundle.is_dir():
            raise ValueError("Production Next.js static bundle is missing")
        if not any(
            b"Sales pulse" in path.read_bytes() or "نبض فروش".encode("utf-8") in path.read_bytes()
            for path in bundle.rglob("*.js")
        ):
            raise ValueError("Compiled production assets are missing the premium sales chart")
        if not any(
            b"Server pulse" in path.read_bytes() or "نبض سرور".encode("utf-8") in path.read_bytes()
            for path in bundle.rglob("*.js")
        ):
            raise ValueError("Compiled production assets are missing the live server resource charts")
        if not any(
            b"Service health" in path.read_bytes() or "وضعیت سرویس‌ها".encode("utf-8") in path.read_bytes()
            for path in bundle.rglob("*.js")
        ):
            raise ValueError("Compiled production assets are missing premium KPIs and operational service health")
        if not any(
            b"SUBSCRIPTION MIX" in path.read_bytes() and b"LATEST TRANSACTIONS" in path.read_bytes()
            for path in bundle.rglob("*.js")
        ):
            raise ValueError("Compiled production assets are missing subscription and payment visuals")
        if not any(
            b"NETWORK TRANSPORTS" in path.read_bytes() and b"PROTOCOL COVERAGE" in path.read_bytes()
            for path in bundle.rglob("*.js")
        ):
            raise ValueError("Compiled production assets are missing the modern tunnel and protocol monitors")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--check-bundle", action="store_true")
    args = parser.parse_args()
    verify_ui_release(args.source, args.main, check_bundle=args.check_bundle)
    print("Sales and server resource charts match latest main and compiled assets")


if __name__ == "__main__":
    main()
