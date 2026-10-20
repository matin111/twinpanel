from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "app" / "transport_candidates" / "gost.py"
SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _constant(name: str):
    for node in TREE.body:
        target = None
        value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            value = node.value
        if isinstance(target, ast.Name) and target.id == name:
            if not isinstance(value, ast.Constant):
                raise AssertionError(f"{name} must be a constant")
            return value.value
    raise AssertionError(f"missing constant: {name}")


def main() -> None:
    keepalive = _constant("TUN_KEEPALIVE_SECONDS")
    settle = _constant("REGISTRATION_SETTLE_SECONDS")

    assert keepalive == 10, keepalive
    assert float(settle) > float(keepalive), (settle, keepalive)

    required = (
        "TWINPANEL_GOST_RELAY_REGISTRATION_V85",
        "?bind=true&nodelay=true",
        "?secure=false&nodelay=true",
        "&keepalive=true&ttl={TUN_KEEPALIVE_SECONDS}s",
        "await asyncio.sleep(REGISTRATION_SETTLE_SECONDS)",
        '"relay_registration_fix": "v85"',
        '"registration_settle_seconds": REGISTRATION_SETTLE_SECONDS',
        "relay_registration=v85",
    )
    for token in required:
        assert token in SOURCE, f"missing GOST V85 contract token: {token}"

    # Relay nodelay has to be symmetric. The GOST connector with nodelay=true
    # sends its request and immediately waits for a response; leaving the Exit
    # handler in delayed-response mode would deadlock before the TUN
    # registration frame can be forwarded.
    server = SOURCE.index("?bind=true&nodelay=true")
    client = SOURCE.index("?secure=false&nodelay=true")
    assert server < client

    # The registration grace must occur after both services/interfaces are
    # installed but before the fail-closed common L3/TCP/UDP probe.
    install = SOURCE.index("await _install_profile_services(")
    settle_pos = SOURCE.index("await asyncio.sleep(REGISTRATION_SETTLE_SECONDS)")
    probe = SOURCE.index("health = await probe(", settle_pos)
    assert install < settle_pos < probe

    print("GOST_RELAY_REGISTRATION_V85_CONTRACT_OK")


if __name__ == "__main__":
    main()
