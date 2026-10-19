#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sys

from app.database import SessionLocal

try:
    from .twinpanel_protocol_cli import PROTOCOL_NAMES, PROTOCOL_ORDER, _managed_nodes, _run
except ImportError:
    from twinpanel_protocol_cli import PROTOCOL_NAMES, PROTOCOL_ORDER, _managed_nodes, _run


def _ascii(value: object) -> str:
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def _read_key(prompt: str) -> str:
    print(prompt, end="", flush=True)
    if sys.stdin.isatty():
        import termios
        import tty

        fd = sys.stdin.fileno()
        previous = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            value = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, previous)
        if value == "\x03":
            raise KeyboardInterrupt
        if not value:
            raise EOFError
        print(value)
        return value

    value = input().strip()
    return value[:1] if value else ""


def _read_choice(prompt: str, maximum: int, *, allow_zero: bool = True) -> int:
    while True:
        raw = _read_key(prompt)
        if raw.isdigit():
            value = int(raw)
            if allow_zero and value == 0:
                return 0
            if 1 <= value <= maximum:
                return value
        print("Invalid selection.")


def _select_protocol() -> str:
    print("Protocols")
    for index, protocol in enumerate(PROTOCOL_ORDER, start=1):
        print(f"  [{index}] {PROTOCOL_NAMES[protocol]}")
    print("  [0] Back")
    print()

    choice = _read_choice("Choose: ", len(PROTOCOL_ORDER))
    if choice == 0:
        raise RuntimeError("CANCELLED")
    return PROTOCOL_ORDER[choice - 1]


def _select_node(db):
    nodes = _managed_nodes(db)

    print("\nTarget")
    for index, row in enumerate(nodes, start=1):
        name = "This server" if getattr(row, "is_mother", False) else _ascii(row.name)
        print(f"  [{index}] {name}  [{row.public_ip}]")
    print("  [0] Back")
    print()

    choice = _read_choice("Choose: ", len(nodes))
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

    print("\nAction")
    for index, (_, title) in enumerate(actions, start=1):
        print(f"  [{index}] {title}")
    print("  [0] Back")
    print()

    choice = _read_choice("Choose: ", len(actions))
    if choice == 0:
        raise RuntimeError("CANCELLED")
    return actions[choice - 1][0]


def _confirm_remove(protocol: str, node) -> bool:
    target = "This server" if getattr(node, "is_mother", False) else _ascii(node.name)
    print("\nConfirm remove")
    print(f"  Target   : {target}")
    print(f"  Protocol : {PROTOCOL_NAMES[protocol]}")
    print("  Backup   : automatic")
    print()
    print("  [1] Remove")
    print("  [0] Cancel")
    print()
    return _read_choice("Choose: ", 1) == 1


def _friendly_error(exc: Exception) -> str:
    value = str(exc)
    if value == "CANCELLED":
        return "Cancelled."

    lowered = value.lower()
    if "invalid transaction" in lowered or "rollback()" in lowered or "pendingrollback" in lowered:
        return "Database transaction was interrupted and rolled back. Retry the action."

    return f"ERROR={_ascii(exc)}"


def _print_result(result: dict) -> None:
    print()
    print("Result   : OK" if result.get("ok") else "Result   : FAILED")

    if result.get("skipped") and result.get("reason") == "already_healthy":
        print("Details  : already healthy")
        return

    backup = result.get("backup")
    if backup:
        print(f"Backup   : {_ascii(backup)}")

    service = result.get("service")
    if service:
        print(f"Service  : {_ascii(service)}")

    detail = result.get("detail") or result.get("message")
    if detail:
        print(f"Details  : {_ascii(detail)}")


def main() -> int:
    db = SessionLocal()
    try:
        protocol = _select_protocol()
        node = _select_node(db)
        action = _select_action()

        if action == "remove" and not _confirm_remove(protocol, node):
            print("Cancelled.")
            return 0

        target = "This server" if getattr(node, "is_mother", False) else _ascii(node.name)
        print(f"\n{PROTOCOL_NAMES[protocol]}  ->  {target}")
        print(f"Action: {action}")

        result = asyncio.run(_run(db, node, protocol, action))
        _print_result(result)
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
