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


def _read_choice(prompt: str, maximum: int, *, allow_zero: bool = True) -> int:
    while True:
        raw = input(prompt).strip()
        if raw.isdigit():
            value = int(raw)
            if allow_zero and value == 0:
                return 0
            if 1 <= value <= maximum:
                return value
        print("Invalid selection.")


def _select_protocol() -> str:
    choice = _read_choice("Protocol [1-5, 0=Back]: ", len(PROTOCOL_ORDER))
    if choice == 0:
        raise RuntimeError("CANCELLED")
    return PROTOCOL_ORDER[choice - 1]


def _select_node(db):
    nodes = _managed_nodes(db)

    print("\nTargets")
    for index, row in enumerate(nodes, start=1):
        name = "Local / This server" if getattr(row, "is_mother", False) else _ascii(row.name)
        mode = "local" if getattr(row, "is_mother", False) else "SSH"
        print(f"  [{index}] {name}  [{row.public_ip}]  ({mode})")
    print("  [0] Back")

    choice = _read_choice("Target: ", len(nodes))
    if choice == 0:
        raise RuntimeError("CANCELLED")
    return nodes[choice - 1]


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
        print(f"  [{index}] {title}")
    print("  [0] Back")

    choice = _read_choice("Action: ", len(actions))
    if choice == 0:
        raise RuntimeError("CANCELLED")
    return actions[choice - 1][0]


def _confirm_remove(protocol: str, node) -> bool:
    target = "Local / This server" if getattr(node, "is_mother", False) else _ascii(node.name)
    print("\nRemove protocol")
    print(f"  Target   : {target}")
    print(f"  Protocol : {PROTOCOL_NAMES[protocol]}")
    print("  Backup   : created before protocol files change")
    print("\n  [1] Continue")
    print("  [0] Cancel")
    return _read_choice("Choose: ", 1) == 1


def _friendly_error(exc: Exception) -> str:
    value = str(exc)
    if value == "CANCELLED":
        return "Cancelled."

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

        if action == "remove" and not _confirm_remove(protocol, node):
            print("Cancelled.")
            return 0

        target = "Local / This server" if getattr(node, "is_mother", False) else _ascii(node.name)
        print(f"\nTarget   : {target} ({node.public_ip})")
        print(f"Protocol : {PROTOCOL_NAMES[protocol]}")
        print(f"Action   : {action}\n")

        result = asyncio.run(_run(db, node, protocol, action))
        if result.get("ok"):
            print("Result   : OK")
        else:
            print("Result   : FAILED")
        details = result.get("detail") or result.get("message")
        if details:
            print(f"Details  : {_ascii(details)}")
        return 0 if result.get("ok") else 1
    except EOFError:
        print("\nInput cancelled.")
        return 130
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except Exception as exc:
        message = _friendly_error(exc)
        if message == "Cancelled.":
            print(message)
            return 0
        print(message, file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
