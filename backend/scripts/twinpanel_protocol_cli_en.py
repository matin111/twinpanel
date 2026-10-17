#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sys

from app.database import SessionLocal

try:
    from .twinpanel_protocol_cli import PROTOCOL_NAMES, PROTOCOL_ORDER, _managed_nodes, _run
except ImportError:
    from twinpanel_protocol_cli import PROTOCOL_NAMES, PROTOCOL_ORDER, _managed_nodes, _run


def _ascii(value: object) -> str:
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def _select_protocol() -> str:
    raw = input("Protocol: ").strip()
    if not raw.isdigit() or not 1 <= int(raw) <= len(PROTOCOL_ORDER):
        raise RuntimeError("INVALID_PROTOCOL")
    return PROTOCOL_ORDER[int(raw) - 1]


def _select_node(db):
    nodes = _managed_nodes(db)

    print("\nTargets")
    for row in nodes:
        name = "Local / This server" if getattr(row, "is_mother", False) else _ascii(row.name)
        mode = "local" if getattr(row, "is_mother", False) else "SSH"
        print(f"  {row.id}) {name}  [{row.public_ip}]  ({mode})")

    raw = input("Target ID: ").strip()
    if not raw.isdigit():
        raise RuntimeError("INVALID_NODE_ID")

    node_id = int(raw)
    node = next((row for row in nodes if int(row.id) == node_id), None)
    if node is None:
        raise RuntimeError("NODE_NOT_FOUND")
    return node


def _select_action() -> str:
    actions = [
        ("status", "Status"),
        ("install", "Install"),
        ("repair", "Repair"),
        ("restart", "Restart"),
        ("remove", "Remove"),
    ]

    print("\nActions")
    for index, (_, title) in enumerate(actions, start=1):
        print(f"  {index}) {title}")

    raw = input("Action: ").strip()
    if not raw.isdigit() or not 1 <= int(raw) <= len(actions):
        raise RuntimeError("INVALID_ACTION")
    return actions[int(raw) - 1][0]


def _friendly_error(exc: Exception) -> str:
    value = str(exc)
    mapping = {
        "INVALID_PROTOCOL": "Invalid protocol selection.",
        "INVALID_NODE_ID": "Invalid target ID.",
        "NODE_NOT_FOUND": "Protocol target not found.",
        "INVALID_ACTION": "Invalid action selection.",
    }
    if value in mapping:
        return mapping[value]

    lowered = value.lower()
    if "invalid transaction" in lowered or "rollback()" in lowered or "pendingrollback" in lowered:
        return "Database transaction was interrupted and rolled back. Retry the action."

    return f"ERROR={_ascii(exc)}"


def main() -> int:
    db = SessionLocal()
    try:
        protocol = _select_protocol()
        node = _select_node(db)
        action = _select_action()

        if action == "remove":
            expected = f"REMOVE {protocol}"
            typed = input(f"Type '{expected}' to confirm: ").strip()
            if typed != expected:
                print("Cancelled")
                return 0

        target = "Local / This server" if getattr(node, "is_mother", False) else _ascii(node.name)
        print(f"\nTarget: {target} ({node.public_ip})")
        print(f"Protocol: {PROTOCOL_NAMES[protocol]}")
        print(f"Action: {action}\n")

        result = asyncio.run(_run(db, node, protocol, action))
        print(json.dumps(result, ensure_ascii=True, indent=2, default=str))
        return 0 if result.get("ok") else 1
    except EOFError:
        print("\nInput cancelled.")
        return 130
    except KeyboardInterrupt:
        print("\nCancelled")
        return 130
    except Exception as exc:
        print(_friendly_error(exc), file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
