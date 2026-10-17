#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.database import SessionLocal
from app.local_core_runtime import ensure_local_core_node
from scripts.twinpanel_protocol_cli import PROTOCOL_NAMES, PROTOCOL_ORDER, _rollback_db, _run


def parse_protocols(raw: str) -> list[str]:
    value = str(raw or "").strip().lower()
    if value in {"all", "*"}:
        return list(PROTOCOL_ORDER)

    aliases = {
        "cisco": "cisco",
        "openconnect": "cisco",
        "openvpn": "openvpn",
        "wireguard": "wireguard",
        "wg": "wireguard",
        "l2tp": "l2tp",
        "ipsec": "l2tp",
        "v2ray": "v2ray",
        "xray": "v2ray",
    }
    selected: list[str] = []
    for token in value.replace(";", ",").replace(" ", ",").split(","):
        token = token.strip()
        if not token:
            continue
        protocol = aliases.get(token)
        if protocol is None:
            raise ValueError(f"Unsupported protocol: {token}")
        if protocol not in selected:
            selected.append(protocol)

    if not selected:
        raise ValueError("No protocols selected")
    return selected


async def install_selected(protocols: list[str]) -> dict:
    db = SessionLocal()
    results: dict[str, dict] = {}
    try:
        node = ensure_local_core_node(db)
        for protocol in protocols:
            try:
                result = await _run(db, node, protocol, "install")
            except Exception as exc:
                _rollback_db(db)
                result = {
                    "ok": False,
                    "action": "install",
                    "protocol": protocol,
                    "target": "local",
                    "error": str(exc),
                }
            results[protocol] = result

        return {
            "ok": all(bool(results[name].get("ok")) for name in protocols),
            "target": "local",
            "node_id": node.id,
            "public_ip": node.public_ip,
            "selected": protocols,
            "results": results,
        }
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install selected TwinPanel VPN protocols on Local / This server."
    )
    parser.add_argument(
        "--protocols",
        required=True,
        help="Comma-separated protocols or 'all'.",
    )
    args = parser.parse_args()

    try:
        protocols = parse_protocols(args.protocols)
    except ValueError as exc:
        print(f"ERROR={exc}", file=sys.stderr)
        return 2

    print("Installing VPN protocols on Local / This server:")
    for protocol in protocols:
        print(f"- {PROTOCOL_NAMES[protocol]}")

    payload = asyncio.run(install_selected(protocols))
    print(json.dumps(payload, ensure_ascii=True, indent=2, default=str))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
