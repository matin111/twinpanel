#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sys

from app.database import SessionLocal
from app.models import NodeProtocolConfig
from app.modern_protocol_models import ModernProtocolSetting
from app.protocol_catalog import PROTOCOL_CATALOG
from app.routers.modern_protocol_admin_v3 import (
    ModernHealthV3In,
    ModernInstallV3In,
    ProtocolProfileIn,
    health as modern_health,
    install as modern_install,
    remove as modern_remove,
)

try:
    from .twinpanel_protocol_cli import (
        PROTOCOL_NAMES as CLASSIC_PROTOCOL_NAMES,
        PROTOCOL_ORDER as CLASSIC_PROTOCOL_ORDER,
        _managed_nodes,
        _run as _run_classic,
    )
except ImportError:
    from twinpanel_protocol_cli import (
        PROTOCOL_NAMES as CLASSIC_PROTOCOL_NAMES,
        PROTOCOL_ORDER as CLASSIC_PROTOCOL_ORDER,
        _managed_nodes,
        _run as _run_classic,
    )

MODERN_PROTOCOL_ORDER = list(PROTOCOL_CATALOG)
PROTOCOL_ORDER = [*CLASSIC_PROTOCOL_ORDER, *MODERN_PROTOCOL_ORDER]
PROTOCOL_NAMES = {
    **CLASSIC_PROTOCOL_NAMES,
    **{key: str(PROTOCOL_CATALOG[key]["title"]) for key in MODERN_PROTOCOL_ORDER},
}


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


def _read_number(prompt: str, maximum: int, *, allow_zero: bool = True) -> int:
    while True:
        raw = input(prompt).strip()
        if raw.isdigit():
            value = int(raw)
            if allow_zero and value == 0:
                return 0
            if 1 <= value <= maximum:
                return value
        print(f"Invalid selection. Use 0-{maximum}.")


def _menu_item(index: int, title: str) -> None:
    print(f"  [{index:>2}] {title}")


def _select_protocol() -> str:
    print("1/3  Protocol")
    print()
    print("  Classic")
    for index, protocol in enumerate(CLASSIC_PROTOCOL_ORDER, start=1):
        _menu_item(index, PROTOCOL_NAMES[protocol])

    print()
    print("  Modern")
    modern_start = len(CLASSIC_PROTOCOL_ORDER) + 1
    for index, protocol in enumerate(MODERN_PROTOCOL_ORDER, start=modern_start):
        _menu_item(index, PROTOCOL_NAMES[protocol])

    print()
    print("  [ 0] Back")
    print()

    # Protocol numbers reach 15, so this page intentionally accepts a complete
    # numeric value followed by Enter. The shorter action page stays one-key.
    choice = _read_number("Choose: ", len(PROTOCOL_ORDER))
    if choice == 0:
        raise RuntimeError("CANCELLED")
    return PROTOCOL_ORDER[choice - 1]


def _select_node(db):
    nodes = _managed_nodes(db)

    print("\n2/3  Server")
    print()
    for index, row in enumerate(nodes, start=1):
        if getattr(row, "is_mother", False):
            label = "This server"
        else:
            name = _ascii(row.name)
            ip = _ascii(row.public_ip or "-")
            label = f"{name:<18} {ip}"
        _menu_item(index, label)
    print()
    print("  [ 0] Back")
    print()

    # Keep one-key navigation for normal small node sets, while still allowing
    # complete numeric node selection if an installation grows beyond 9 nodes.
    if len(nodes) <= 9:
        choice = _read_choice("Choose: ", len(nodes))
    else:
        choice = _read_number("Choose: ", len(nodes))
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

    print("\n3/3  Action")
    print()
    for index, (_, title) in enumerate(actions, start=1):
        _menu_item(index, title)
    print()
    print("  [ 0] Back")
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
    if protocol in CLASSIC_PROTOCOL_ORDER:
        print("  Backup   : automatic")
    print()
    print("  [1] Remove")
    print("  [0] Cancel")
    print()
    return _read_choice("Choose: ", 1) == 1


def _safe_saved_settings(row: ModernProtocolSetting | None) -> dict:
    if row is None:
        return {}
    try:
        value = json.loads(row.settings_json or "{}")
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _modern_install_payload(db, node, protocol: str) -> ModernInstallV3In:
    status = (
        db.query(NodeProtocolConfig)
        .filter(
            NodeProtocolConfig.node_id == int(node.id),
            NodeProtocolConfig.protocol == protocol,
        )
        .first()
    )
    setting = (
        db.query(ModernProtocolSetting)
        .filter(
            ModernProtocolSetting.node_id == int(node.id),
            ModernProtocolSetting.protocol == protocol,
        )
        .first()
    )

    port = int(
        status.port
        if status is not None and status.port
        else PROTOCOL_CATALOG[protocol]["default_port"]
    )
    preset = str(setting.preset_name or "recommended") if setting is not None else "recommended"
    profile = ProtocolProfileIn(
        preset=preset,
        settings=_safe_saved_settings(setting),
    )
    return ModernInstallV3In(
        protocols=[protocol],
        ports={protocol: port},
        profiles={protocol: profile},
    )


def _modern_result(protocol: str, action: str, node, payload: dict) -> dict:
    item = (payload.get("protocols") or {}).get(protocol) or {}
    ok = bool(payload.get("ok"))
    detail = item.get("error") or item.get("detail") or item.get("message")
    if not detail and action in {"repair", "restart"} and ok:
        detail = "saved profile reapplied"
    return {
        "ok": ok,
        "action": action,
        "protocol": protocol,
        "target": "local" if getattr(node, "is_mother", False) else "remote",
        "service": item.get("service"),
        "detail": detail,
        "result": payload,
    }


async def _run_modern(db, node, protocol: str, action: str) -> dict:
    if action == "status":
        result = await modern_health(
            int(node.id),
            ModernHealthV3In(protocols=[protocol]),
            db,
        )
        return _modern_result(protocol, action, node, result)

    if action == "remove":
        result = await modern_remove(int(node.id), protocol, db)
        return {
            "ok": bool(result.get("ok", True)),
            "action": action,
            "protocol": protocol,
            "target": "local" if getattr(node, "is_mother", False) else "remote",
            "service": result.get("service"),
            "detail": result.get("error") or result.get("message"),
            "result": result,
        }

    if action in {"install", "repair", "restart"}:
        if action == "install":
            try:
                current = await modern_health(
                    int(node.id),
                    ModernHealthV3In(protocols=[protocol]),
                    db,
                )
                current_item = (current.get("protocols") or {}).get(protocol) or {}
                if current_item.get("ok"):
                    return {
                        "ok": True,
                        "action": action,
                        "protocol": protocol,
                        "target": "local" if getattr(node, "is_mother", False) else "remote",
                        "skipped": True,
                        "reason": "already_healthy",
                        "service": current_item.get("service"),
                        "result": current,
                    }
            except Exception:
                db.rollback()

        install_payload = _modern_install_payload(db, node, protocol)
        result = await modern_install(int(node.id), install_payload, db)
        return _modern_result(protocol, action, node, result)

    raise RuntimeError("INVALID_ACTION")


async def _run(db, node, protocol: str, action: str) -> dict:
    if protocol in CLASSIC_PROTOCOL_ORDER:
        return await _run_classic(db, node, protocol, action)
    if protocol in MODERN_PROTOCOL_ORDER:
        return await _run_modern(db, node, protocol, action)
    raise RuntimeError("INVALID_PROTOCOL")


def _friendly_error(exc: Exception) -> str:
    value = str(exc)
    if value == "CANCELLED":
        return "Cancelled."

    lowered = value.lower()
    if "invalid transaction" in lowered or "rollback()" in lowered or "pendingrollback" in lowered:
        return "Database transaction was interrupted and rolled back. Retry the action."

    detail = getattr(exc, "detail", None)
    if detail is not None:
        return f"ERROR={_ascii(detail)}"
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
        print(f"\n{PROTOCOL_NAMES[protocol]} > {target} > {action.title()}")

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
        db.rollback()
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
