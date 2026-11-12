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
    if not all(marker in component for marker in ("Sales pulse", "salesAnalytics", "seriesVisible", "selectPointer")):
        # Deliberately specific: fail rather than publish a look-alike or a stub.
        raise ValueError("Premium chart interactive feature markers are missing")
    if "@media(prefers-reduced-motion:reduce)" not in css:
        raise ValueError("Premium chart reduced-motion accessibility has been dropped")

    if check_bundle:
        bundle = source / ".next/standalone/.next/static"
        if not bundle.is_dir():
            raise ValueError("Production Next.js static bundle is missing")
        if not any(
            b"Sales pulse" in path.read_bytes() or "نبض فروش".encode("utf-8") in path.read_bytes()
            for path in bundle.rglob("*.js")
        ):
            raise ValueError("Compiled production assets are missing the premium sales chart")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--main", type=Path, required=True)
    parser.add_argument("--check-bundle", action="store_true")
    args = parser.parse_args()
    verify_ui_release(args.source, args.main, check_bundle=args.check_bundle)
    print("Premium sales dashboard is present and matches latest main")


if __name__ == "__main__":
    main()
