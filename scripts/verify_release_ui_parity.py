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
    "components/legacy-subscriptions-exact.tsx",
    "components/admin-users-runtime.tsx",
    "components/central-app-brand-studio.css",
    "app/node-observability-v1.css",
    "components/legacy-nodes-runtime-v2.tsx",
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
        "reported online nodes", "classify(t.status)", "latency(t.latency_ms)"
    )):
        raise ValueError("Tunnel/protocol status, grouping, or honest telemetry logic missing")
    if not all(marker in network_css for marker in (
        'html[data-theme="light"]', "prefers-reduced-motion:reduce",
        ".protocolGrid", ".tunnelRoute", ".protocolState"
    )):
        raise ValueError("Modern tunnel/protocol theme or accessibility styles are missing")
    if not all(marker in lower for marker in ("fleetSummary", "nodeRole")):
        raise ValueError("Modern node fleet status summary or role badges missing")

    # The dark-mode-only admin roster cards rendered unreadable when the
    # global page theme became light. Keep explicit, scoped light-mode rules
    # for subscriptions, users, and the branded app settings editor.
    roster_subs = (source / PROTECTED_FILES[11]).read_text(encoding="utf-8")
    roster_users = (source / PROTECTED_FILES[12]).read_text(encoding="utf-8")
    brand_css = (source / PROTECTED_FILES[13]).read_text(encoding="utf-8")
    if not all(marker in roster_subs for marker in (
        'html[data-theme="light"] .legacy-subscriptions-page .mobile-subscription-card',
        'html[data-theme="light"] .legacy-subscriptions-page .mobile-subscription-identities b',
        'html[data-theme="light"] .legacy-subscriptions-page .mobile-subscription-usage',
        'html[data-theme="light"] .legacy-subscriptions-page .subscription-presence-offline',
        "mobile-subscription-actions", "toggleStatus(item)"
    )):
        raise ValueError("Subscription roster light-mode contrast or actions are missing")
    if not all(marker in roster_users for marker in (
        'html[data-theme="light"] .admin-users-runtime .admin-user-card',
        'html[data-theme="light"] .admin-users-runtime .admin-user-contact',
        'html[data-theme="light"] .admin-users-runtime .admin-user-action',
        'html[data-theme="light"] .admin-users-runtime .admin-user-account-count',
        "adminApi.usersFastPage", "adminApi.toggleUser"
    )):
        raise ValueError("User roster light-mode contrast or actions are missing")
    if not all(marker in brand_css for marker in (
        'html[data-theme="light"] .tbs-page',
        'html[data-theme="light"] .tbs-page .tbs-tabs',
        'html[data-theme="light"] .tbs-page .tbs-readonly',
        'html[data-theme="light"] .tbs-page .tbs-preview',
        'html[data-theme="light"] .tbs-page .tbs-save:disabled'
    )):
        raise ValueError("App Brand Studio light-mode input, tab, or preview contrast is missing")

    node_css = (source / PROTECTED_FILES[14]).read_text(encoding="utf-8")
    node_view = (source / PROTECTED_FILES[15]).read_text(encoding="utf-8")
    if not all(marker in node_css for marker in (
        'html[data-theme="light"] .legacy-control-page .node-list-quick-filters .node-list-filter-card.active',
        'html[data-theme="light"] .legacy-control-page .node-list-quick-filters .node-list-stat-text b',
        'html[data-theme="light"] .legacy-control-page .node-list-quick-filters .stat-icon',
        'html[data-theme="light"] .legacy-control-page .table .primary-soft',
        'html[data-theme="light"] .legacy-control-page .runtime-toolbar input',
        '#f3edff', '#1b2942'
    )):
        raise ValueError("Admin node list light-mode KPI, table or controls are missing")
    if not all(marker in node_view for marker in (
        'node-list-quick-filters', 'node-list-filter-card', 'aria-pressed={filter===item.id}',
        'node-list-filter-summary', 'selectFilter(item.id)'
    )):
        raise ValueError("Admin node status quick filters or actual node counts are missing")

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
            b"Subscription overview" in path.read_bytes() and b"Recent activity" in path.read_bytes()
            for path in bundle.rglob("*.js")
        ):
            raise ValueError("Compiled production assets are missing subscription and payment visuals")
        if not any(
            b"Tunnel monitor" in path.read_bytes() and b"Service protocols" in path.read_bytes()
            for path in bundle.rglob("*.js")
        ):
            raise ValueError("Compiled production assets are missing the modern tunnel and protocol monitors")
        # Validate the actual browser-delivered bundles as well as checked-in
        # source so a stale Next.js artifact cannot silently ship dark roster
        # cards under a light page theme.
        light_sub = b'html[data-theme="light"] .legacy-subscriptions-page .mobile-subscription-card'
        light_user = b'html[data-theme="light"] .admin-users-runtime .admin-user-card'
        compiled_js = tuple(bundle.rglob("*.js"))
        for marker, screen in (
            (light_sub, "subscription"),
            (light_user, "user"),
        ):
            if not any(marker in path.read_bytes() for path in compiled_js):
                raise ValueError(f"Compiled production assets are missing {screen} light-mode card styles")
        if not any(
            b'html[data-theme=light] .tbs-page .tbs-tabs' in path.read_bytes()
            and b'--tbs-input:#f8faff' in path.read_bytes()
            for path in bundle.rglob("*.css")
        ):
            raise ValueError("Compiled production CSS is missing App Brand Studio light-mode styles")


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
